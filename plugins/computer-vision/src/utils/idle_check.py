"""User idle detection via GetLastInputInfo for time-share fallback.

When Windows Sandbox is unavailable, the plugin falls back to time-share
mode: it detects user idle periods and briefly uses SendInput during those
windows. This module provides the idle detection logic.

Synthetic input tracking prevents our own injected input from being
counted as user activity, which would cause a deadlock.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import time

logger = logging.getLogger(__name__)

# Track the tick count of our most recent synthetic input
_last_synthetic_input_tick: int = 0

# Tolerance for matching synthetic input ticks (ms)
_SYNTHETIC_TOLERANCE_MS = 200


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def mark_synthetic_input() -> None:
    """Record that we just injected synthetic input.

    Call this from send_mouse_click / type_unicode_string so that
    GetLastInputInfo doesn't mistake our own input for user activity.
    """
    global _last_synthetic_input_tick
    if sys.platform != "win32":
        return
    _last_synthetic_input_tick = ctypes.windll.kernel32.GetTickCount()


def is_user_idle(threshold_ms: int = 2000, force: bool = False) -> bool:
    """Check if the user has been idle for at least *threshold_ms* milliseconds.

    Args:
        threshold_ms: Minimum idle time in milliseconds (default 2000).
        force: If True, always return True (skip the check). Prevents deadlocks.

    Returns:
        True if the user is idle (or force=True or non-Windows platform).
        False if the user has provided input within the threshold.
    """
    if force:
        return True

    if sys.platform != "win32":
        return True

    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)

        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            logger.warning("GetLastInputInfo failed")
            return True  # assume idle on failure

        current_tick = ctypes.windll.kernel32.GetTickCount()
        idle_ms = current_tick - lii.dwTime

        # Check if the last input was our own synthetic input
        if _last_synthetic_input_tick > 0:
            synthetic_delta = abs(int(lii.dwTime) - _last_synthetic_input_tick)
            if synthetic_delta <= _SYNTHETIC_TOLERANCE_MS:
                # Last input was ours — treat as idle
                return True

        return idle_ms >= threshold_ms

    except Exception as exc:
        logger.warning("Idle check failed: %s", exc)
        return True  # assume idle on error
