"""MCP tool for mouse scroll operations."""

from __future__ import annotations

import ctypes
import logging

import win32gui

from src.server import mcp
from src.errors import make_error, make_success, INPUT_FAILED, INVALID_INPUT, ACCESS_DENIED
from src.coordinates import normalize_for_sendinput, validate_coordinates, to_screen_absolute
from src.utils.security import (
    validate_hwnd_range,
    validate_hwnd_fresh,
    check_restricted,
    check_rate_limit,
    guard_dry_run,
    log_action,
)
from src.utils.win32_input import send_mouse_scroll
from src.utils.win32_window import focus_window
from src.utils.action_helpers import _get_hwnd_process_name, _capture_post_action, _build_window_state

logger = logging.getLogger(__name__)

VALID_DIRECTIONS = ("up", "down", "left", "right")


@mcp.tool()
def cv_scroll(
    hwnd: int,
    direction: str = "down",
    amount: int = 3,
    x: int | None = None,
    y: int | None = None,
    screenshot: bool = True,
    screenshot_delay_ms: int = 150,
) -> dict:
    """Scroll a window in a given direction.

    Args:
        hwnd: Window handle to scroll (required).
        direction: Scroll direction - "up", "down", "left", or "right".
        amount: Number of scroll notches (1-20, default 3). Each notch = 120 units.
        x: Optional X position for scroll target (window-relative). Defaults to window center.
        y: Optional Y position for scroll target (window-relative). Defaults to window center.
        screenshot: Whether to capture a screenshot after scrolling (default True).
        screenshot_delay_ms: Delay in ms before screenshot capture (default 150).
    """
    try:
        # Validate direction
        if direction not in VALID_DIRECTIONS:
            return make_error(
                INVALID_INPUT,
                f"Invalid direction: {direction!r}. Must be one of {VALID_DIRECTIONS}.",
            )

        # Clamp amount to valid range
        amount = max(1, min(amount, 20))

        # Full security gate
        validate_hwnd_range(hwnd)
        if not validate_hwnd_fresh(hwnd):
            return make_error(INPUT_FAILED, f"HWND {hwnd} is no longer valid.")

        process_name = _get_hwnd_process_name(hwnd)
        if not process_name:
            return make_error(ACCESS_DENIED, "Cannot determine process for HWND")

        check_restricted(process_name)
        check_rate_limit()

        params = {"hwnd": hwnd, "direction": direction, "amount": amount, "x": x, "y": y}
        dry = guard_dry_run("cv_scroll", params)
        if dry is not None:
            return dry

        log_action("cv_scroll", params, "start")

        # Focus the target window
        focus_window(hwnd)

        # Determine scroll position
        if x is not None and y is not None:
            screen_x, screen_y = to_screen_absolute(x, y, hwnd)
            if not validate_coordinates(screen_x, screen_y):
                return make_error(
                    INVALID_INPUT,
                    f"Coordinates ({screen_x}, {screen_y}) outside virtual desktop.",
                )
        else:
            # Default to window center
            rect = win32gui.GetWindowRect(hwnd)
            screen_x = (rect[0] + rect[2]) // 2
            screen_y = (rect[1] + rect[3]) // 2

        # Normalize for SendInput
        norm_x, norm_y = normalize_for_sendinput(screen_x, screen_y)

        # Send scroll
        ok = send_mouse_scroll(norm_x, norm_y, direction, amount)
        log_action("cv_scroll", params, "ok" if ok else "fail")

        if not ok:
            return make_error(INPUT_FAILED, "SendInput failed for scroll")

        # Build result
        result = make_success(action="scroll", direction=direction, amount=amount)
        if screenshot:
            image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
            if image_path:
                result["image_path"] = image_path
        window_state = _build_window_state(hwnd)
        if window_state:
            result["window_state"] = window_state
        return result

    except Exception as e:
        return make_error(INPUT_FAILED, str(e))
