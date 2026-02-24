"""Plugin configuration loaded from environment variables with sensible defaults."""

from __future__ import annotations

import os
from pathlib import Path


def _get_env_list(key: str, default: str) -> list[str]:
    """Get a comma-separated list from an environment variable."""
    raw = os.environ.get(key, default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _get_env_bool(key: str, default: bool) -> bool:
    """Get a boolean from an environment variable."""
    raw = os.environ.get(key, "")
    if not raw:
        return default
    return raw.lower() in ("true", "1", "yes")


def _get_env_int(key: str, default: int) -> int:
    """Get an integer from an environment variable."""
    raw = os.environ.get(key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Restricted processes — blocked from input injection by default
RESTRICTED_PROCESSES: list[str] = _get_env_list(
    "CV_RESTRICTED_PROCESSES",
    "credential manager,keepass,1password,bitwarden,windows security",
)

# Dry-run mode — returns planned actions without executing
DRY_RUN: bool = _get_env_bool("CV_DRY_RUN", False)

# Default max width for screenshot downscaling
DEFAULT_MAX_WIDTH: int = _get_env_int("CV_DEFAULT_MAX_WIDTH", 1280)

# Max text length for type_text
MAX_TEXT_LENGTH: int = _get_env_int("CV_MAX_TEXT_LENGTH", 1000)

# Rate limit — max input actions per second
RATE_LIMIT: int = _get_env_int("CV_RATE_LIMIT", 20)

# Audit log path
AUDIT_LOG_PATH: Path = Path(
    os.environ.get(
        "CV_AUDIT_LOG_PATH",
        os.path.join(os.environ.get("LOCALAPPDATA", "."), "claude-cv-plugin", "audit.jsonl"),
    )
)

# OCR redaction patterns — regex patterns to redact from OCR output
# Default patterns: SSN and credit card numbers
_DEFAULT_PII_PATTERNS = r"\b\d{3}-\d{2}-\d{4}\b,\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
OCR_REDACTION_PATTERNS: list[str] = _get_env_list(
    "CV_OCR_REDACTION_PATTERNS", _DEFAULT_PII_PATTERNS
)

# Max wait timeout for synchronization tools
MAX_WAIT_TIMEOUT: float = 60.0

# Max simple wait duration
MAX_SIMPLE_WAIT: float = 30.0

# UI Automation default depth
DEFAULT_UIA_DEPTH: int = 5

# UI Automation timeout in seconds
UIA_TIMEOUT: float = 5.0
