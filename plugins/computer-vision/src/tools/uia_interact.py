"""MCP tools for UI Automation interaction — click buttons, list elements."""

from __future__ import annotations

import logging

from src.errors import INVALID_INPUT, UIA_ERROR, make_error, make_success
from src.server import mcp
from src.utils.action_helpers import _build_window_state, _capture_post_action, _get_hwnd_process_name
from src.utils.security import (
    check_restricted,
    log_action,
    validate_hwnd_fresh,
    validate_hwnd_range,
)

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_click_ui(
    hwnd: int,
    name: str,
    control_type: str | None = None,
    screenshot: bool = True,
    screenshot_delay_ms: int = 300,
) -> dict:
    """Click a UI element by name using UI Automation — works on WinUI 3, UWP, WPF, Win32.

    **Why this exists**: ``SendInput`` mouse clicks are ignored by WinUI 3 toolbar
    buttons (Windows 11 Paint, Calculator, etc.). This tool bypasses mouse input
    entirely — it finds the element by name in the UIA accessibility tree and
    invokes it directly via TogglePattern, InvokePattern, or LegacyIAccessible.

    **When to use**: Use this to click toolbar buttons, menu items, checkboxes,
    and other UI controls that don't respond to ``cv_mouse_click``. For canvas
    interactions (drawing, dragging), use ``cv_mouse_click`` or ``cv_record``.

    **How it works**:
    1. Searches all descendants of the window for an element matching ``name``
    2. Tries UIA patterns in order: Invoke → Toggle → SelectionItem → LegacyIAccessible
    3. Returns which pattern was used (for debugging)

    Args:
        hwnd: Window handle to search in.
        name: Exact name of the UI element (e.g. "Elipse", "Rectángulo", "Guardar").
              Use ``cv_read_ui`` first to discover element names.
        control_type: Optional filter — "Button", "ListItem", "MenuItem", etc.
        screenshot: Whether to capture a screenshot after clicking. Default True.
        screenshot_delay_ms: Delay before screenshot in ms. Default 300.
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
        log_action("cv_click_ui", {"hwnd": hwnd}, "ACCESS_DENIED")
        return make_error(INVALID_INPUT, str(exc))

    # Map control_type string to ID
    ctrl_type_id = None
    if control_type:
        from src.utils.uia_click import CONTROL_TYPE_NAMES
        name_to_id = {v: k for k, v in CONTROL_TYPE_NAMES.items()}
        ctrl_type_id = name_to_id.get(control_type)

    # Find and invoke the element
    from src.utils.uia_click import click_ui_element
    success, method = click_ui_element(hwnd, name, ctrl_type_id)

    if not success:
        log_action("cv_click_ui", {"hwnd": hwnd, "name": name}, "NOT_FOUND")
        return make_error(UIA_ERROR, method)

    log_action("cv_click_ui", {"hwnd": hwnd, "name": name, "method": method}, "OK")

    result = make_success(
        action="click_ui",
        element_name=name,
        method=method,
    )

    if screenshot:
        image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
        if image_path:
            result["image_path"] = image_path

    window_state = _build_window_state(hwnd)
    if window_state:
        result["window_state"] = window_state

    return result
