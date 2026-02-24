"""MCP tool for finding UI elements by natural language query."""

from __future__ import annotations

import ctypes
import logging
import time as _time
from difflib import SequenceMatcher

import win32gui

from src.server import mcp
from src.errors import (
    FIND_NO_MATCH,
    INVALID_INPUT,
    UIA_ERROR,
    make_error,
    make_success,
)
from src.models import FindMatch, Point, Rect, UiaElement
from src.utils.security import (
    validate_hwnd_fresh,
    validate_hwnd_range,
    check_restricted,
    get_process_name_by_pid,
    log_action,
)
from src.utils.uia import get_ui_tree

logger = logging.getLogger(__name__)

# Per-HWND screenshot cooldown to avoid spamming captures on repeated no-match calls
_screenshot_cooldowns: dict[int, float] = {}
_SCREENSHOT_COOLDOWN = 5.0  # seconds between screenshots for same HWND


def _can_screenshot(hwnd: int) -> bool:
    """Check if enough time has elapsed since last screenshot for this HWND."""
    last = _screenshot_cooldowns.get(hwnd)
    if last is None:
        return True
    return _time.monotonic() - last >= _SCREENSHOT_COOLDOWN


# Fuzzy match threshold -- minimum SequenceMatcher ratio to consider a match
_MATCH_THRESHOLD = 0.5

# Substring match gets this fixed score
_SUBSTRING_SCORE = 0.7

# Boost added when query matches control_type exactly
_CONTROL_TYPE_BOOST = 0.15


def _get_process_name_from_hwnd(hwnd: int) -> str:
    """Get the process name for a window handle."""
    try:
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""
        return get_process_name_by_pid(pid.value)
    except Exception:
        return ""


def _flatten_uia_tree(elements: list[UiaElement]) -> list[UiaElement]:
    """Recursively flatten a UIA element tree into a flat list."""
    flat: list[UiaElement] = []
    for el in elements:
        flat.append(el)
        if el.children:
            flat.extend(_flatten_uia_tree(el.children))
    return flat


def _fuzzy_score(query: str, text: str) -> float:
    """Compute fuzzy match score between query and text.

    Returns a score in [0.0, 1.0]. Uses the best of:
    - SequenceMatcher ratio
    - Substring match (fixed 0.7)
    """
    if not query or not text:
        return 0.0

    q = query.lower()
    t = text.lower()

    # Substring match
    if q in t:
        return max(_SUBSTRING_SCORE, SequenceMatcher(None, q, t).ratio())

    # Pure fuzzy ratio
    return SequenceMatcher(None, q, t).ratio()


def _match_uia(query: str, hwnd: int) -> list[FindMatch]:
    """Search UIA tree for elements matching query.

    Returns list of FindMatch sorted by confidence descending.
    """
    try:
        tree = get_ui_tree(hwnd, depth=8, filter="all")
    except Exception as exc:
        logger.debug("UIA tree walk failed for HWND %d: %s", hwnd, exc)
        return []

    flat = _flatten_uia_tree(tree)
    q_lower = query.lower()
    matches: list[FindMatch] = []

    for el in flat:
        # Skip elements with zero-size bounding boxes
        if el.rect.width <= 0 or el.rect.height <= 0:
            continue

        best_score = 0.0

        # Match against element name
        if el.name:
            best_score = max(best_score, _fuzzy_score(query, el.name))

        # Match against element value
        if el.value:
            best_score = max(best_score, _fuzzy_score(query, el.value))

        # Boost if query matches control type exactly
        if el.control_type and q_lower == el.control_type.lower():
            best_score = max(best_score, _MATCH_THRESHOLD + _CONTROL_TYPE_BOOST)

        # Also check if query is a substring of control_type or vice versa
        if el.control_type and q_lower in el.control_type.lower():
            best_score = max(best_score, _SUBSTRING_SCORE)

        if best_score >= _MATCH_THRESHOLD:
            matches.append(
                FindMatch(
                    text=el.name or el.value or el.control_type,
                    bbox=el.rect,
                    confidence=min(best_score, 1.0),
                    source="uia",
                    ref_id=el.ref_id,
                    control_type=el.control_type,
                )
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def _match_ocr(query: str, hwnd: int) -> list[FindMatch]:
    """Search OCR output for text matching query.

    Returns list of FindMatch sorted by confidence descending.
    """
    from src.utils.ocr_engine import _engine
    from src.utils.screenshot import capture_window_raw

    try:
        rect = win32gui.GetWindowRect(hwnd)
    except Exception as exc:
        logger.debug("GetWindowRect failed for HWND %d: %s", hwnd, exc)
        return []

    image = capture_window_raw(hwnd)
    if image is None:
        logger.debug("capture_window_raw returned None for HWND %d", hwnd)
        return []

    try:
        ocr_result = _engine.recognize(
            image,
            preprocess=True,
            origin=Point(x=rect[0], y=rect[1]),
        )
    except Exception as exc:
        logger.debug("OCR recognition failed for HWND %d: %s", hwnd, exc)
        return []

    regions = ocr_result.get("regions", [])
    matches: list[FindMatch] = []

    for idx, region in enumerate(regions):
        # Region can be OcrRegion model or dict
        if hasattr(region, "text"):
            region_text = region.text
            region_bbox = region.bbox
        else:
            region_text = region.get("text", "")
            bbox_data = region.get("bbox", {})
            region_bbox = Rect(
                x=bbox_data.get("x", 0),
                y=bbox_data.get("y", 0),
                width=bbox_data.get("width", 0),
                height=bbox_data.get("height", 0),
            )

        if not region_text:
            continue

        score = _fuzzy_score(query, region_text)
        if score >= _MATCH_THRESHOLD:
            # Convert Rect model to Rect if needed
            if isinstance(region_bbox, Rect):
                bbox = region_bbox
            else:
                bbox = Rect(
                    x=getattr(region_bbox, "x", 0),
                    y=getattr(region_bbox, "y", 0),
                    width=getattr(region_bbox, "width", 0),
                    height=getattr(region_bbox, "height", 0),
                )

            matches.append(
                FindMatch(
                    text=region_text,
                    bbox=bbox,
                    confidence=min(score, 1.0),
                    source="ocr",
                    ref_id=f"ocr_{idx}",
                    control_type=None,
                )
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def _filter_bbox_in_window(matches: list[FindMatch], hwnd: int) -> list[FindMatch]:
    """Remove matches whose bbox falls outside the window bounds."""
    try:
        rect = win32gui.GetWindowRect(hwnd)
        win_left, win_top, win_right, win_bottom = rect
    except Exception:
        return matches  # If we can't get window rect, keep all matches

    filtered: list[FindMatch] = []
    for m in matches:
        m_left = m.bbox.x
        m_top = m.bbox.y
        m_right = m.bbox.x + m.bbox.width
        m_bottom = m.bbox.y + m.bbox.height

        # Check that the match bbox is at least partially within the window
        if m_right <= win_left or m_left >= win_right:
            continue
        if m_bottom <= win_top or m_top >= win_bottom:
            continue

        filtered.append(m)

    return filtered


@mcp.tool()
def cv_find(
    query: str,
    hwnd: int,
    method: str = "auto",
    max_results: int = 20,
) -> dict:
    """Find elements on a window using natural language.

    Searches using UIA (UI Automation) first for native app elements,
    then falls back to OCR for visual text matching.

    When image_path is returned, use image_scale and window_origin to map visual
    coordinates: screen_x = window_origin.x + (image_x / image_scale),
    screen_y = window_origin.y + (image_y / image_scale)

    Args:
        query: Natural language description of what to find (e.g., "search bar", "submit button").
        hwnd: Window handle to search in.
        method: Search method - "auto" (UIA first, OCR fallback), "uia", or "ocr".
        max_results: Maximum number of matches to return (1-50, default 20).
    """
    # --- Input validation ---
    if method not in ("auto", "uia", "ocr"):
        return make_error(INVALID_INPUT, f"Invalid method '{method}'. Must be 'auto', 'uia', or 'ocr'.")

    if not query or not query.strip():
        return make_error(INVALID_INPUT, "Query must not be empty.")

    # Cap query length
    if len(query) > 500:
        query = query[:500]

    # Clamp max_results
    max_results = max(1, min(max_results, 50))

    # --- Security gates ---
    try:
        validate_hwnd_range(hwnd)
    except ValueError as exc:
        return make_error(INVALID_INPUT, str(exc))

    if not validate_hwnd_fresh(hwnd):
        return make_error(INVALID_INPUT, f"Window handle {hwnd} is no longer valid.")

    process_name = _get_process_name_from_hwnd(hwnd)
    try:
        check_restricted(process_name)
    except Exception as exc:
        log_action("cv_find", {"hwnd": hwnd, "query": query}, "ACCESS_DENIED")
        return make_error(INVALID_INPUT, str(exc))

    # --- Search ---
    matches: list[FindMatch] = []
    method_used = method

    if method == "uia":
        matches = _match_uia(query, hwnd)
        method_used = "uia"
    elif method == "ocr":
        matches = _match_ocr(query, hwnd)
        method_used = "ocr"
    else:
        # Auto mode: UIA first, OCR fallback (sequential, no threads)
        matches = _match_uia(query, hwnd)
        method_used = "uia"
        if not matches:
            matches = _match_ocr(query, hwnd)
            method_used = "ocr"

    # --- Bbox validation ---
    matches = _filter_bbox_in_window(matches, hwnd)

    # --- Log and return ---
    log_action(
        "cv_find",
        {"hwnd": hwnd, "query": query, "method": method, "max_results": max_results},
        "OK" if matches else "NO_MATCH",
    )

    if not matches:
        error = make_error(
            FIND_NO_MATCH,
            f"No elements matching '{query}' found in window {hwnd} using {method_used}.",
        )
        # Vision fallback: attach a screenshot so Claude can visually inspect the window
        if _can_screenshot(hwnd):
            try:
                from src.utils.screenshot import capture_window

                capture_result = capture_window(hwnd, max_width=1280)
                _screenshot_cooldowns[hwnd] = _time.monotonic()
                error["error"]["image_path"] = capture_result.image_path
                error["error"]["message"] = (
                    f"No elements matching '{query}' found. "
                    "Use Read tool on image_path to visually inspect the window."
                )
                # Add scale metadata for coordinate mapping
                rect_for_scale = win32gui.GetWindowRect(hwnd)
                pw = rect_for_scale[2] - rect_for_scale[0]
                if pw > 0:
                    error["image_scale"] = min(pw, 1280) / pw
                    error["window_origin"] = {"x": rect_for_scale[0], "y": rect_for_scale[1]}
            except Exception:
                pass  # Capture failure: return normal error without image_path
        return error

    result = make_success(
        matches=[m.model_dump() for m in matches[:max_results]],
        match_count=len(matches),
        method_used=method_used,
    )

    # Always capture screenshot on success (no cooldown for success path)
    try:
        from src.utils.screenshot import capture_window

        capture_result = capture_window(hwnd, max_width=1280)
        result["image_path"] = capture_result.image_path

        # Compute image_scale: ratio of saved image width to physical window width
        rect = win32gui.GetWindowRect(hwnd)
        physical_width = rect[2] - rect[0]
        if physical_width > 0:
            saved_width = min(physical_width, 1280)
            result["image_scale"] = saved_width / physical_width

        # Window origin for coordinate mapping
        result["window_origin"] = {"x": rect[0], "y": rect[1]}
    except Exception:
        pass  # Screenshot failure doesn't block the success response

    # Add window state metadata
    from src.utils.action_helpers import _build_window_state

    window_state = _build_window_state(hwnd)
    if window_state:
        result["window_state"] = window_state

    return result
