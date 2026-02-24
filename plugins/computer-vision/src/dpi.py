"""DPI awareness initialization and per-monitor scaling helpers."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

logger = logging.getLogger(__name__)

# DPI awareness constants
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
MONITOR_DEFAULTTONEAREST = 2


def init_dpi_awareness() -> bool:
    """Initialize per-monitor DPI awareness v2 for the process.

    Must be called before any Win32 API calls to ensure all coordinates
    are in physical pixels.

    Returns True if DPI awareness was set successfully.
    """
    try:
        result = ctypes.windll.user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        if result:
            logger.info("DPI awareness set to PER_MONITOR_AWARE_V2")
            return True
        # Fallback to older API
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        logger.info("DPI awareness set via SetProcessDpiAwareness (fallback)")
        return True
    except (OSError, AttributeError) as e:
        logger.warning("Failed to set DPI awareness: %s", e)
        return False


def get_monitor_dpi(hmonitor: int) -> tuple[int, int]:
    """Get the DPI for a specific monitor.

    Returns (dpi_x, dpi_y) tuple. Defaults to (96, 96) on failure.
    """
    dpi_x = ctypes.c_uint()
    dpi_y = ctypes.c_uint()
    try:
        # MDT_EFFECTIVE_DPI = 0
        ctypes.windll.shcore.GetDpiForMonitor(
            ctypes.c_void_p(hmonitor), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        )
        return (dpi_x.value, dpi_y.value)
    except (OSError, AttributeError):
        return (96, 96)


def get_window_dpi(hwnd: int) -> int:
    """Get the DPI for the monitor containing a specific window."""
    try:
        return ctypes.windll.user32.GetDpiForWindow(hwnd)
    except (OSError, AttributeError):
        return 96


def physical_to_logical(x: int, y: int, dpi: int) -> tuple[int, int]:
    """Convert physical pixel coordinates to logical coordinates."""
    scale = dpi / 96.0
    return (int(x / scale), int(y / scale))


def logical_to_physical(x: int, y: int, dpi: int) -> tuple[int, int]:
    """Convert logical coordinates to physical pixel coordinates."""
    scale = dpi / 96.0
    return (int(x * scale), int(y * scale))


def get_scale_factor(dpi: int) -> float:
    """Get the scale factor for a given DPI value."""
    return dpi / 96.0
