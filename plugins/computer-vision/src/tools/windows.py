"""MCP tools for window listing, focusing, and moving/resizing."""

from __future__ import annotations

import logging

import win32con
import win32gui

from src.errors import (
    INVALID_INPUT,
    WINDOW_NOT_FOUND,
    make_error,
    make_success,
    CVPluginError,
)
from src.models import Rect
from src.server import mcp
from src.utils.security import (
    check_rate_limit,
    check_restricted,
    guard_dry_run,
    log_action,
    validate_hwnd_fresh,
    get_process_name_by_pid,
)
from src.utils.win32_window import (
    enum_windows,
    focus_window,
    get_window_info,
    move_window,
)

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_list_windows(include_children: bool = False) -> dict:
    """List all visible windows with title, process, class, position, and monitor.

    Args:
        include_children: If True, also list child windows for each top-level window.
    """
    try:
        windows = enum_windows(include_children=include_children)
        return make_success(
            windows=[w.model_dump() for w in windows],
            count=len(windows),
        )
    except Exception as exc:
        logger.error("cv_list_windows failed: %s", exc)
        return make_error(WINDOW_NOT_FOUND, f"Failed to enumerate windows: {exc}")


@mcp.tool()
def cv_focus_window(hwnd: int) -> dict:
    """Bring a window to the foreground by its HWND.

    Restores the window if minimized, then activates it.

    Args:
        hwnd: The window handle to focus.
    """
    try:
        # Security gates
        if not validate_hwnd_fresh(hwnd):
            return make_error(WINDOW_NOT_FOUND, f"Window HWND {hwnd} no longer exists")

        info = get_window_info(hwnd)
        check_restricted(info.process_name)
        check_rate_limit()

        dry = guard_dry_run("cv_focus_window", {"hwnd": hwnd})
        if dry is not None:
            return dry

        success = focus_window(hwnd)
        log_action("cv_focus_window", {"hwnd": hwnd}, "ok" if success else "failed")

        if success:
            return make_success(hwnd=hwnd, focused=True)
        return make_error(WINDOW_NOT_FOUND, f"Failed to focus window HWND {hwnd}")

    except CVPluginError as exc:
        return exc.to_dict()
    except Exception as exc:
        logger.error("cv_focus_window failed: %s", exc)
        return make_error(WINDOW_NOT_FOUND, f"Failed to focus window: {exc}")


@mcp.tool()
def cv_move_window(
    hwnd: int,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    action: str | None = None,
) -> dict:
    """Move, resize, minimize, maximize, or restore a window.

    Provide x/y/width/height to reposition, or use action for state changes.

    Args:
        hwnd: The window handle.
        x: New left position (optional, keeps current if None).
        y: New top position (optional, keeps current if None).
        width: New width (optional, keeps current if None).
        height: New height (optional, keeps current if None).
        action: One of "maximize", "minimize", "restore" (optional).
    """
    try:
        # Security gates
        if not validate_hwnd_fresh(hwnd):
            return make_error(WINDOW_NOT_FOUND, f"Window HWND {hwnd} no longer exists")

        info = get_window_info(hwnd)
        check_restricted(info.process_name)
        check_rate_limit()

        params = {
            "hwnd": hwnd,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "action": action,
        }
        dry = guard_dry_run("cv_move_window", params)
        if dry is not None:
            return dry

        # Handle action-based state changes
        if action is not None:
            action_lower = action.lower()
            if action_lower == "maximize":
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            elif action_lower == "minimize":
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            elif action_lower == "restore":
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                return make_error(
                    INVALID_INPUT,
                    f"Invalid action '{action}'. Use 'maximize', 'minimize', or 'restore'.",
                )

            log_action("cv_move_window", params, "ok")
            updated_info = get_window_info(hwnd)
            return make_success(
                hwnd=hwnd,
                action=action_lower,
                rect=updated_info.rect.model_dump(),
            )

        # Handle position/size move
        current_rect = info.rect
        new_x = x if x is not None else current_rect.x
        new_y = y if y is not None else current_rect.y
        new_width = width if width is not None else current_rect.width
        new_height = height if height is not None else current_rect.height

        new_rect = move_window(hwnd, new_x, new_y, new_width, new_height)
        log_action("cv_move_window", params, "ok")

        return make_success(hwnd=hwnd, rect=new_rect.model_dump())

    except CVPluginError as exc:
        return exc.to_dict()
    except Exception as exc:
        logger.error("cv_move_window failed: %s", exc)
        return make_error(WINDOW_NOT_FOUND, f"Failed to move window: {exc}")
