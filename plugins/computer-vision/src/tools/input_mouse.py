"""MCP tool for mouse input: click, double-click, and drag operations."""

from __future__ import annotations

import ctypes
import logging

from src.server import mcp
from src.errors import make_error, make_success, INPUT_FAILED, INVALID_INPUT
from src.coordinates import to_screen_absolute, normalize_for_sendinput, validate_coordinates
from src.utils.security import (
    check_restricted,
    check_rate_limit,
    guard_dry_run,
    log_action,
    get_process_name_by_pid,
)
from src.utils.win32_input import send_mouse_click, send_mouse_drag
from src.utils.win32_window import focus_window
from src.utils.action_helpers import _capture_post_action, _build_window_state

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_mouse_click(
    x: int,
    y: int,
    button: str = "left",
    click_type: str = "single",
    hwnd: int | None = None,
    coordinate_space: str = "screen_absolute",
    start_x: int | None = None,
    start_y: int | None = None,
    screenshot: bool = True,
    screenshot_delay_ms: int = 150,
) -> dict:
    """Click, double-click, or drag the mouse at a screen position.

    Args:
        x: X coordinate of the target (or drag end point).
        y: Y coordinate of the target (or drag end point).
        button: Mouse button - "left", "right", or "middle".
        click_type: "single" or "double".
        hwnd: Optional window handle. When set, auto-focuses the window first.
        coordinate_space: "screen_absolute" or "window_relative" (requires hwnd).
        start_x: If provided along with start_y, performs a drag from (start_x, start_y) to (x, y).
        start_y: If provided along with start_x, performs a drag from (start_x, start_y) to (x, y).
        screenshot: Whether to capture a screenshot after the action (default True, requires hwnd).
        screenshot_delay_ms: Delay in milliseconds before capturing the post-action screenshot (default 150).
    """
    try:
        # Validate button
        if button not in ("left", "right", "middle"):
            return make_error(INVALID_INPUT, f"Invalid button: {button!r}. Must be left, right, or middle.")

        # Validate click_type
        if click_type not in ("single", "double"):
            return make_error(INVALID_INPUT, f"Invalid click_type: {click_type!r}. Must be single or double.")

        is_drag = start_x is not None and start_y is not None

        # Convert window-relative to screen-absolute if needed
        if coordinate_space == "window_relative" and hwnd:
            x, y = to_screen_absolute(x, y, hwnd)
            if is_drag:
                start_x, start_y = to_screen_absolute(start_x, start_y, hwnd)

        # Auto-focus window if hwnd provided
        if hwnd:
            try:
                focus_window(hwnd)
            except Exception as e:
                logger.warning("Failed to focus window %d: %s", hwnd, e)

        # Security gate: check foreground window's process
        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        if fg_hwnd:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
            process_name = get_process_name_by_pid(pid.value)
            if process_name:
                check_restricted(process_name)

        check_rate_limit()

        params = {
            "x": x, "y": y, "button": button, "click_type": click_type,
        }
        if is_drag:
            params["start_x"] = start_x
            params["start_y"] = start_y

        dry = guard_dry_run("cv_mouse_click", params)
        if dry is not None:
            return dry

        if is_drag:
            # Validate both start and end coordinates
            if not validate_coordinates(start_x, start_y):
                return make_error(INVALID_INPUT, f"Start coordinates ({start_x}, {start_y}) outside virtual desktop.")
            if not validate_coordinates(x, y):
                return make_error(INVALID_INPUT, f"End coordinates ({x}, {y}) outside virtual desktop.")

            norm_sx, norm_sy = normalize_for_sendinput(start_x, start_y)
            norm_ex, norm_ey = normalize_for_sendinput(x, y)
            ok = send_mouse_drag(norm_sx, norm_sy, norm_ex, norm_ey, button)
            log_action("cv_mouse_click", params, "ok" if ok else "fail")
            if not ok:
                return make_error(INPUT_FAILED, "SendInput failed for mouse drag.")
            result = make_success(
                action="drag",
                start={"x": start_x, "y": start_y},
                end={"x": x, "y": y},
                button=button,
            )
            if screenshot and hwnd:
                image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
                if image_path:
                    result["image_path"] = image_path
            if hwnd:
                window_state = _build_window_state(hwnd)
                if window_state:
                    result["window_state"] = window_state
            return result
        else:
            # Regular click
            if not validate_coordinates(x, y):
                return make_error(INVALID_INPUT, f"Coordinates ({x}, {y}) outside virtual desktop.")

            norm_x, norm_y = normalize_for_sendinput(x, y)
            ok = send_mouse_click(norm_x, norm_y, button, click_type)
            log_action("cv_mouse_click", params, "ok" if ok else "fail")
            if not ok:
                return make_error(INPUT_FAILED, "SendInput failed for mouse click.")
            result = make_success(
                action="click",
                position={"x": x, "y": y},
                button=button,
                click_type=click_type,
            )
            if screenshot and hwnd:
                image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
                if image_path:
                    result["image_path"] = image_path
            if hwnd:
                window_state = _build_window_state(hwnd)
                if window_state:
                    result["window_state"] = window_state
            return result

    except Exception as e:
        return make_error(INPUT_FAILED, str(e))
