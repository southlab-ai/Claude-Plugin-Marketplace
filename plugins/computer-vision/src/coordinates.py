"""Coordinate transformation utilities for screen-absolute and window-relative systems."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

logger = logging.getLogger(__name__)

# Virtual desktop metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def get_virtual_desktop_bounds() -> tuple[int, int, int, int]:
    """Get the virtual desktop bounds (x, y, width, height).

    The virtual desktop spans all monitors and can have negative coordinates.
    """
    x = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return (x, y, w, h)


def validate_coordinates(x: int, y: int) -> bool:
    """Check if coordinates are within the virtual desktop bounds."""
    vx, vy, vw, vh = get_virtual_desktop_bounds()
    return vx <= x < vx + vw and vy <= y < vy + vh


def to_screen_absolute(x: int, y: int, hwnd: int) -> tuple[int, int]:
    """Convert window-relative coordinates to screen-absolute.

    Uses the window's client area origin as the reference point.
    """
    point = ctypes.wintypes.POINT(x, y)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point))
    return (point.x, point.y)


def to_window_relative(x: int, y: int, hwnd: int) -> tuple[int, int]:
    """Convert screen-absolute coordinates to window-relative.

    Uses the window's client area origin as the reference point.
    """
    point = ctypes.wintypes.POINT(x, y)
    ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point))
    return (point.x, point.y)


def normalize_for_sendinput(x: int, y: int) -> tuple[int, int]:
    """Normalize screen coordinates to 0-65535 range for SendInput MOUSEINPUT.

    SendInput with MOUSEEVENTF_ABSOLUTE uses a 0-65535 coordinate range
    mapped to the full virtual desktop.
    """
    vx, vy, vw, vh = get_virtual_desktop_bounds()
    norm_x = int(((x - vx) * 65535) / (vw - 1))
    norm_y = int(((y - vy) * 65535) / (vh - 1))
    return (max(0, min(65535, norm_x)), max(0, min(65535, norm_y)))
