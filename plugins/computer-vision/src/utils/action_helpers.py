"""Shared helpers for mutating tool actions: post-action screenshots and window state."""

from __future__ import annotations

import ctypes
import logging
import time

import win32gui

from src.utils.screenshot import capture_window
from src.utils.security import get_process_name_by_pid

logger = logging.getLogger(__name__)


def _build_window_state(hwnd: int) -> dict | None:
    """Build window state metadata dict for tool responses.

    Returns: {"hwnd": int, "title": str, "is_foreground": bool, "rect": {...}} or None on failure.
    """
    try:
        title = win32gui.GetWindowText(hwnd)
        fg = ctypes.windll.user32.GetForegroundWindow()
        rect = win32gui.GetWindowRect(hwnd)
        return {
            "hwnd": hwnd,
            "title": title,
            "is_foreground": fg == hwnd,
            "rect": {
                "x": rect[0], "y": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1],
            },
        }
    except Exception:
        return None


def _capture_post_action(hwnd: int, delay_ms: int = 150, max_width: int = 1280) -> str | None:
    """Capture screenshot after a mutating action. Returns image_path or None."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    try:
        result = capture_window(hwnd, max_width=max_width)
        return result.image_path
    except Exception:
        logger.debug("Post-action screenshot failed for HWND %s", hwnd, exc_info=True)
        return None


def _get_hwnd_process_name(hwnd: int) -> str:
    """Get process name for an hwnd. Returns empty string on failure."""
    try:
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""
        return get_process_name_by_pid(pid.value)
    except Exception:
        return ""
