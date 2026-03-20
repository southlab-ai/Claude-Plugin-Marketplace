"""MCP tool for recording actions with rapid screenshot capture and command log."""

from __future__ import annotations

import logging
import time

import win32gui
from PIL import Image

from src.coordinates import normalize_for_sendinput, validate_coordinates
from src.errors import CAPTURE_FAILED, INPUT_FAILED, INVALID_INPUT, make_error, make_success
from src.server import mcp
from src.utils.action_helpers import _build_window_state, _get_hwnd_process_name
from src.utils.screenshot import capture_window_raw, save_image
from src.utils.security import (
    check_rate_limit,
    check_restricted,
    log_action,
    validate_hwnd_fresh,
    validate_hwnd_range,
)
from src.utils.win32_input import send_mouse_click, send_mouse_move
from src.utils.win32_window import focus_window

logger = logging.getLogger(__name__)


def _capture_frame(hwnd: int, max_width: int = 1280) -> str | None:
    """Capture a single frame. Returns image path or None."""
    try:
        img = capture_window_raw(hwnd)
        if img is None:
            return None
        return save_image(img, max_width=max_width)
    except Exception:
        return None


@mcp.tool()
def cv_record(
    hwnd: int,
    action: str = "move_click",
    x: int = 0,
    y: int = 0,
    end_x: int | None = None,
    end_y: int | None = None,
    button: str = "left",
    click_type: str = "single",
    coordinate_space: str = "screen_absolute",
    move_duration_ms: int = 300,
    move_steps: int = 25,
    frames_before: int = 1,
    frames_after: int = 5,
    frame_interval_ms: int = 100,
    max_width: int = 1280,
) -> dict:
    """Execute a mouse action with human-like cursor movement and capture rapid
    screenshots before, during, and after — producing a frame-by-frame replay.

    **Purpose**: This is the primary tool for interacting with applications that
    require realistic mouse behavior. Many apps (UWP, WebView, games) ignore
    teleported clicks and need real ``WM_MOUSEMOVE`` events along the cursor path.
    The ``move_click`` action solves this by smoothly moving the cursor with
    smoothstep interpolation before clicking.

    **Frame log**: Each frame in the response has:
    - ``t_ms``: Elapsed time since the action started
    - ``action``: What happened at this moment (e.g. "move_start", "hover", "click", "after +200ms")
    - ``image_path``: Screenshot captured at this moment — use Read tool to view

    **Debugging with frames**: Compare before/after frames to verify your click
    landed on the right target. If an element shook or flashed, it means the move
    was invalid. If nothing changed, the click may have missed. Review intermediate
    frames to see exactly where the cursor was during movement.

    Actions:
    - ``move_click`` (recommended): Smooth move → 50ms hover → click. Use this for most interactions.
    - ``move``: Smooth move without clicking. Use to trigger hover states.
    - ``click``: Instant click without movement. Use only when cursor is already positioned.
    - ``drag``: Smooth move to start → mouse-down → smooth move to end → mouse-up.

    Args:
        hwnd: Window handle to record.
        action: Action type — "move_click", "move", "click", or "drag".
        x: Target X coordinate (or drag start for "drag"). Use center_screen from cv_scene.
        y: Target Y coordinate (or drag start for "drag"). Use center_screen from cv_scene.
        end_x: Drag end X (only for "drag" action).
        end_y: Drag end Y (only for "drag" action).
        button: Mouse button — "left", "right", or "middle".
        click_type: "single" or "double".
        coordinate_space: "screen_absolute", "window_relative", or "window_capture".
        move_duration_ms: Duration of smooth cursor movement in ms. Default 300.
        move_steps: Number of interpolation steps for movement. Default 25.
        frames_before: Screenshots to capture before the action. Default 1.
        frames_after: Screenshots to capture after the action. Default 5.
        frame_interval_ms: Delay between consecutive after-frames in ms. Default 100.
        max_width: Maximum image width for frames. Default 1280.
    """
    if action not in ("move_click", "move", "click", "drag"):
        return make_error(INVALID_INPUT, f"Invalid action '{action}'. Use move_click, move, click, or drag.")

    if action == "drag" and (end_x is None or end_y is None):
        return make_error(INVALID_INPUT, "drag action requires end_x and end_y.")

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
        log_action("cv_record", {"hwnd": hwnd}, "ACCESS_DENIED")
        return make_error(INVALID_INPUT, str(exc))

    check_rate_limit()

    # Convert coordinates
    if coordinate_space == "window_capture":
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y = rect[0] + x, rect[1] + y
            if end_x is not None:
                end_x, end_y = rect[0] + end_x, rect[1] + end_y
        except Exception:
            pass
    elif coordinate_space == "window_relative":
        from src.coordinates import to_screen_absolute
        x, y = to_screen_absolute(x, y, hwnd)
        if end_x is not None:
            end_x, end_y = to_screen_absolute(end_x, end_y, hwnd)

    if not validate_coordinates(x, y):
        return make_error(INVALID_INPUT, f"Coordinates ({x}, {y}) outside virtual desktop.")

    # Focus window
    try:
        focus_window(hwnd)
    except Exception:
        pass

    frames: list[dict] = []
    t0 = time.monotonic()

    def _snap(label: str) -> None:
        path = _capture_frame(hwnd, max_width)
        elapsed = int((time.monotonic() - t0) * 1000)
        frames.append({"t_ms": elapsed, "action": label, "image_path": path})

    # --- Before frames ---
    for i in range(frames_before):
        _snap("before")
        if i < frames_before - 1:
            time.sleep(frame_interval_ms / 1000.0)

    # --- Execute action ---
    norm_x, norm_y = normalize_for_sendinput(x, y)

    if action == "move_click":
        _snap(f"move_start → ({x},{y})")
        send_mouse_move(norm_x, norm_y, steps=move_steps, duration_ms=move_duration_ms)
        _snap(f"hover ({x},{y})")
        time.sleep(0.05)  # 50ms hover
        send_mouse_click(norm_x, norm_y, button, click_type)
        _snap(f"click ({x},{y}) {button} {click_type}")

    elif action == "move":
        _snap(f"move_start → ({x},{y})")
        send_mouse_move(norm_x, norm_y, steps=move_steps, duration_ms=move_duration_ms)
        _snap(f"move_end ({x},{y})")

    elif action == "click":
        send_mouse_click(norm_x, norm_y, button, click_type)
        _snap(f"click ({x},{y}) {button} {click_type}")

    elif action == "drag":
        norm_ex, norm_ey = normalize_for_sendinput(end_x, end_y)
        _snap(f"move_start → ({x},{y})")
        send_mouse_move(norm_x, norm_y, steps=move_steps, duration_ms=move_duration_ms)
        _snap(f"drag_start ({x},{y}) → ({end_x},{end_y})")
        time.sleep(0.05)

        from src.utils.win32_input import send_mouse_drag
        send_mouse_drag(norm_x, norm_y, norm_ex, norm_ey, button, move_duration_ms)
        _snap(f"drag_end ({end_x},{end_y})")

    # --- After frames ---
    for i in range(frames_after):
        time.sleep(frame_interval_ms / 1000.0)
        _snap(f"after +{(i + 1) * frame_interval_ms}ms")

    total_ms = int((time.monotonic() - t0) * 1000)
    log_action("cv_record", {"hwnd": hwnd, "action": action, "x": x, "y": y, "frames": len(frames)}, "OK")

    result = make_success(
        frames=frames,
        frame_count=len(frames),
        total_ms=total_ms,
        action_summary=f"{action} at ({x},{y})",
    )

    window_state = _build_window_state(hwnd)
    if window_state:
        result["window_state"] = window_state

    return result
