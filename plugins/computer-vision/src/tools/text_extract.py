"""MCP tool for extracting all visible text from a window via UIA or OCR."""

from __future__ import annotations

import logging

import win32gui
import win32process

from src.server import mcp
from src.errors import (
    make_error,
    make_success,
    INVALID_INPUT,
    WINDOW_NOT_FOUND,
    CAPTURE_FAILED,
    OCR_UNAVAILABLE,
    UIA_ERROR,
)
from src.models import Point, UiaElement
from src.utils.security import (
    validate_hwnd_range,
    validate_hwnd_fresh,
    check_restricted,
    get_process_name_by_pid,
    log_action,
    _apply_redaction_patterns,
)
from src import config
from src.utils.uia import get_ui_tree

logger = logging.getLogger(__name__)

# Control types whose text content should be collected
TEXT_CONTROL_TYPES = {"Text", "Edit", "Document", "ListItem", "DataItem"}

# Row grouping threshold (pixels) for spatial sorting
_ROW_HEIGHT = 20

# Y-gap threshold (pixels) for inserting paragraph breaks
_PARAGRAPH_GAP = 40


def _flatten_uia_tree(elements: list[UiaElement]) -> list[UiaElement]:
    """Recursively flatten a UIA element tree into a single list."""
    flat: list[UiaElement] = []
    for el in elements:
        flat.append(el)
        if el.children:
            flat.extend(_flatten_uia_tree(el.children))
    return flat


def _extract_uia_text(hwnd: int) -> tuple[str, float]:
    """Extract text from a window using UI Automation.

    Returns (text, confidence) where confidence is 1.0 for UIA.
    """
    tree = get_ui_tree(hwnd, depth=10, filter="all")
    flat = _flatten_uia_tree(tree)

    # Collect text-bearing elements
    text_elements: list[tuple[int, int, str]] = []
    for el in flat:
        if el.control_type not in TEXT_CONTROL_TYPES:
            continue
        if not el.name and not el.value:
            continue

        # For Edit/Document, prefer value over name if value is non-empty
        if el.control_type in ("Edit", "Document") and el.value:
            content = el.value
        else:
            content = el.name

        if not content:
            continue

        text_elements.append((el.rect.y, el.rect.x, content))

    if not text_elements:
        return ("", 1.0)

    # Spatial sorting: group by row (y // _ROW_HEIGHT), then left-to-right
    text_elements.sort(key=lambda t: (t[0] // _ROW_HEIGHT, t[1]))

    # Join with newlines, inserting paragraph breaks for large y-gaps
    parts: list[str] = []
    prev_y: int | None = None
    for y, _x, content in text_elements:
        if prev_y is not None and (y - prev_y) > _PARAGRAPH_GAP:
            parts.append("")  # extra blank line for paragraph break
        parts.append(content)
        prev_y = y

    text = "\n".join(parts)
    return (text, 1.0)


def _extract_ocr_text(hwnd: int) -> tuple[str, float]:
    """Extract text from a window using OCR.

    Returns (text, confidence).
    """
    from src.utils.ocr_engine import _engine
    from src.utils.screenshot import capture_window_raw

    rect = win32gui.GetWindowRect(hwnd)
    image = capture_window_raw(hwnd)
    if image is None:
        return ("", 0.0)

    result = _engine.recognize(
        image,
        preprocess=True,
        origin=Point(x=rect[0], y=rect[1]),
    )

    regions = result.get("regions", [])
    confidence = result.get("confidence", 0.0)

    if not regions:
        return (result.get("text", ""), confidence)

    # Spatial sorting of regions
    sorted_regions: list[tuple[int, int, str]] = []
    for region in regions:
        bbox = region.bbox if hasattr(region, "bbox") else None
        if bbox is None:
            continue
        ry = bbox.y if hasattr(bbox, "y") else bbox.get("y", 0)
        rx = bbox.x if hasattr(bbox, "x") else bbox.get("x", 0)
        rtext = region.text if hasattr(region, "text") else region.get("text", "")
        sorted_regions.append((ry, rx, rtext))

    sorted_regions.sort(key=lambda t: (t[0] // _ROW_HEIGHT, t[1]))

    parts: list[str] = []
    prev_y: int | None = None
    for y, _x, content in sorted_regions:
        if prev_y is not None and (y - prev_y) > _PARAGRAPH_GAP:
            parts.append("")
        parts.append(content)
        prev_y = y

    text = "\n".join(parts)
    return (text, confidence)


@mcp.tool()
def cv_get_text(
    hwnd: int,
    method: str = "auto",
) -> dict:
    """Extract text from a window using UI Automation or OCR.

    Uses UIA for native Windows apps (perfect accuracy), falls back to OCR
    for Chrome/Electron apps where UIA returns minimal content.

    Args:
        hwnd: Window handle to extract text from.
        method: Extraction method - "auto" (UIA first, OCR fallback), "uia", or "ocr".
    """
    # Validate method parameter
    if method not in ("auto", "uia", "ocr"):
        return make_error(INVALID_INPUT, f"Invalid method '{method}'. Must be 'auto', 'uia', or 'ocr'.")

    # Security gates
    try:
        validate_hwnd_range(hwnd)
    except ValueError as e:
        return make_error(INVALID_INPUT, str(e))

    if not validate_hwnd_fresh(hwnd):
        return make_error(WINDOW_NOT_FOUND, f"Window HWND {hwnd} no longer exists.")

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = get_process_name_by_pid(pid)
        check_restricted(process_name)
    except Exception as e:
        if "restricted" in str(e).lower() or "access denied" in str(e).lower():
            return make_error("ACCESS_DENIED", str(e))
        process_name = ""

    log_action("cv_get_text", {"hwnd": hwnd, "method": method}, "started")

    try:
        text = ""
        source = ""
        confidence = 0.0

        if method == "uia":
            text, confidence = _extract_uia_text(hwnd)
            source = "uia"
        elif method == "ocr":
            text, confidence = _extract_ocr_text(hwnd)
            source = "ocr"
        else:
            # Auto mode: try UIA first, fall back to OCR if insufficient
            text, confidence = _extract_uia_text(hwnd)
            source = "uia"
            if len(text) < 20:
                ocr_text, ocr_confidence = _extract_ocr_text(hwnd)
                text = ocr_text
                confidence = ocr_confidence
                source = "ocr"

        # Apply PII redaction to all output
        text = _apply_redaction_patterns(text, config.OCR_REDACTION_PATTERNS)

        log_action("cv_get_text", {"hwnd": hwnd, "method": method}, "success")

        return make_success(
            text=text,
            source=source,
            line_count=text.count("\n") + 1,
            confidence=confidence,
        )

    except TimeoutError as e:
        log_action("cv_get_text", {"hwnd": hwnd, "method": method}, "timeout")
        return make_error(UIA_ERROR, f"UI Automation timed out: {e}")
    except Exception as e:
        log_action("cv_get_text", {"hwnd": hwnd, "method": method}, "error")
        logger.exception("cv_get_text failed for HWND %d", hwnd)
        return make_error(CAPTURE_FAILED, f"Text extraction failed: {e}")
