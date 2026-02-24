"""Central security gate: restricted processes, HWND freshness, rate limiting, audit logging, dry-run."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import ctypes

from src import config
from src.errors import AccessDeniedError, RateLimitedError, make_error

logger = logging.getLogger(__name__)

# Rate limiter state
_action_timestamps: list[float] = []


def validate_hwnd_range(hwnd: int) -> None:
    """Validate that an HWND is within the valid Win32 range.

    Raises ValueError if hwnd is out of range.
    """
    if not (0 < hwnd <= 0xFFFFFFFF):
        raise ValueError(f"Invalid HWND: {hwnd}. Must be in range (0, 0xFFFFFFFF].")


def check_restricted(process_name: str) -> None:
    """Check if a process is in the restricted list. Raises AccessDeniedError if restricted."""
    if process_name.lower() in config.RESTRICTED_PROCESSES:
        raise AccessDeniedError(process_name)


def get_process_name_by_pid(pid: int) -> str:
    """Get process name from PID. Returns empty string on failure."""
    try:
        import win32api
        import win32process
        import win32con

        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        try:
            exe = win32process.GetModuleFileNameEx(handle, 0)
            return Path(exe).stem.lower()
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""


def validate_hwnd_fresh(hwnd: int) -> bool:
    """Validate that an HWND still refers to a valid window (TOCTOU prevention).

    Returns True if the window is valid.
    """
    return bool(ctypes.windll.user32.IsWindow(hwnd))


def check_rate_limit() -> None:
    """Check if the rate limit has been exceeded. Raises RateLimitedError if so."""
    now = time.monotonic()
    # Remove timestamps older than 1 second
    cutoff = now - 1.0
    while _action_timestamps and _action_timestamps[0] < cutoff:
        _action_timestamps.pop(0)

    if len(_action_timestamps) >= config.RATE_LIMIT:
        raise RateLimitedError()

    _action_timestamps.append(now)


def guard_dry_run(tool_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """If dry-run mode is enabled, return the planned action without executing.

    Returns None if dry-run is disabled (proceed with execution).
    Returns a dict describing the planned action if dry-run is enabled.
    """
    if not config.DRY_RUN:
        return None
    return make_error(
        "DRY_RUN",
        f"Dry-run mode: would execute {tool_name} with params: {_sanitize_params(params)}",
    )


def log_action(tool_name: str, params: dict[str, Any], result_status: str) -> None:
    """Log an action to the structured audit log."""
    try:
        config.AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tool": tool_name,
            "params": _sanitize_params(params),
            "result": result_status,
        }
        with open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


def _apply_redaction_patterns(text: str, patterns: list[str]) -> str:
    """Apply regex redaction patterns to a string."""
    for pattern in patterns:
        if not pattern:
            continue
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            text = regex.sub("[REDACTED]", text)
        except re.error:
            continue
    return text


def redact_ocr_output(text: str, regions: list[Any]) -> tuple[str, list[Any]]:
    """Apply redaction patterns to OCR output.

    Accepts regions as list[dict] or list[OcrRegion] (Pydantic models).
    Returns (redacted_text, redacted_regions) preserving the input type.
    """
    patterns = config.OCR_REDACTION_PATTERNS
    if not patterns:
        return text, regions

    redacted_text = _apply_redaction_patterns(text, patterns)

    redacted_regions = []
    for region in regions:
        # Support both dict and Pydantic BaseModel (OcrRegion)
        if hasattr(region, "model_copy"):
            # Pydantic v2 model
            r = region.model_copy(deep=True)
            r.text = _apply_redaction_patterns(r.text, patterns)
            # Also redact word-level text if present
            if hasattr(r, "words") and r.words:
                for word in r.words:
                    word.text = _apply_redaction_patterns(word.text, patterns)
            redacted_regions.append(r)
        else:
            # Plain dict
            r = dict(region)
            r["text"] = _apply_redaction_patterns(r.get("text", ""), patterns)
            redacted_regions.append(r)

    return redacted_text, redacted_regions


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Sanitize parameters for logging — replace text content with length."""
    sanitized = {}
    for key, value in params.items():
        if key in ("text",) and isinstance(value, str):
            sanitized[key] = f"[TEXT len={len(value)}]"
        else:
            sanitized[key] = value
    return sanitized
