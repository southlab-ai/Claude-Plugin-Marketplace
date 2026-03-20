"""MCP tool for scene analysis — annotated screenshots with detected elements."""

from __future__ import annotations

import logging

import win32gui
from PIL import Image

from src.errors import CAPTURE_FAILED, INVALID_INPUT, make_error, make_success
from src.server import mcp
from src.utils.action_helpers import _build_window_state, _get_hwnd_process_name
from src.utils.scene_analysis import (
    add_screen_coordinates,
    annotate_image,
    detect_elements,
    label_with_ocr,
)
from src.utils.screenshot import capture_window_raw, save_image
from src.utils.security import (
    check_restricted,
    log_action,
    validate_hwnd_fresh,
    validate_hwnd_range,
)

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_scene(
    hwnd: int,
    max_width: int = 1280,
    label: bool = True,
    min_area: int = 600,
) -> dict:
    """Detect all UI elements in a window and return an annotated screenshot with numbered bounding boxes.

    **Purpose**: Before interacting with any application, call this tool to get a map
    of all clickable elements with their precise screen coordinates. This replaces
    visual guessing — each element has ``center_screen`` coordinates you can pass
    directly to ``cv_mouse_click`` or ``cv_record``.

    **How it works**: Uses multi-strategy OpenCV contour detection (Canny edges,
    multi-level binary threshold, HSV saturation filter) to find rectangular elements
    like buttons, cards, input fields, panels, and slots. Non-maximum suppression
    removes duplicates. Elements are sorted top-to-bottom, left-to-right.

    **Output**: Returns ``image_path`` (annotated screenshot with cyan numbered boxes)
    and ``elements[]`` — each with:
    - ``id``: Sequential number matching the annotation
    - ``label``: OCR text found inside the element (if ``label=True``)
    - ``bbox``: ``{x, y, width, height}`` in image coordinates
    - ``center``: ``{x, y}`` center in image coordinates
    - ``center_screen``: ``{x, y}`` center in screen-absolute coordinates — **use these for clicking**

    **Important**: Use the Read tool on ``image_path`` to visually inspect the
    annotated screenshot. You are a multimodal LLM — read the actual card values,
    button labels, and element content with your vision, not just the OCR labels.
    OCR labels help with text-based UI elements but are unreliable on graphical
    content like playing cards or icons.

    **Workflow**: ``cv_scene`` (plan) → ``cv_record`` with move_click (act) → Read frame images (verify)

    Args:
        hwnd: Window handle to analyze.
        max_width: Maximum width for the output image. Default 1280.
        label: Whether to run OCR to label detected elements. Default True.
        min_area: Minimum element area in pixels to detect. Default 600.
    """
    # Security gates
    try:
        validate_hwnd_range(hwnd)
    except ValueError as exc:
        return make_error(INVALID_INPUT, str(exc))

    if not validate_hwnd_fresh(hwnd):
        return make_error(INVALID_INPUT, f"Window handle {hwnd} is no longer valid.")

    process_name = _get_hwnd_process_name(hwnd)
    try:
        check_restricted(process_name)
    except Exception as exc:
        log_action("cv_scene", {"hwnd": hwnd}, "ACCESS_DENIED")
        return make_error(INVALID_INPUT, str(exc))

    # Capture raw image
    img = capture_window_raw(hwnd)
    if img is None:
        return make_error(CAPTURE_FAILED, f"Failed to capture window HWND {hwnd}")

    # Window position for screen-absolute mapping
    try:
        rect = win32gui.GetWindowRect(hwnd)
        win_x, win_y = rect[0], rect[1]
    except Exception:
        win_x, win_y = 0, 0

    # Detect elements
    try:
        elements = detect_elements(img, min_area=min_area)
    except ImportError as exc:
        return make_error(INVALID_INPUT, str(exc))
    except Exception as exc:
        logger.error("Scene detection failed: %s", exc)
        return make_error(CAPTURE_FAILED, f"Scene analysis failed: {exc}")

    # OCR labeling
    if label and elements:
        label_with_ocr(elements, img)

    # Add screen-absolute coordinates
    add_screen_coordinates(elements, win_x, win_y)

    # Downscale for display
    physical_w, physical_h = img.width, img.height
    display_img = img.copy()
    if display_img.width > max_width:
        ratio = max_width / display_img.width
        new_h = int(display_img.height * ratio)
        display_img = display_img.resize((max_width, new_h), Image.Resampling.LANCZOS)

    # Draw annotations on downscaled image
    annotated = annotate_image(
        display_img, elements, src_width=physical_w, src_height=physical_h,
    )

    # Save (max_width=annotated.width to prevent double downscale in save_image)
    filepath = save_image(annotated, max_width=annotated.width)

    log_action("cv_scene", {"hwnd": hwnd, "elements": len(elements)}, "OK")

    result = make_success(
        image_path=filepath,
        elements=elements,
        element_count=len(elements),
    )

    window_state = _build_window_state(hwnd)
    if window_state:
        result["window_state"] = window_state

    return result
