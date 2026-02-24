"""MCP tools for window synchronization and waiting."""

from __future__ import annotations

import asyncio
import ctypes
import logging
import re

from src.server import mcp
from src.errors import INVALID_INPUT, make_error, make_success
from src import config

logger = logging.getLogger(__name__)


def _enum_windows_by_title(pattern: re.Pattern[str]) -> tuple[int, str] | None:
    """Enumerate windows and return the first (hwnd, title) matching the pattern.

    Uses ctypes EnumWindows to avoid importing win32gui (keeping this module lightweight).
    """
    # Callback types for EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32 = ctypes.windll.user32

    result: list[tuple[int, str]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if pattern.search(title):
            result.append((hwnd, title))
            return False  # Stop enumeration
        return True

    enum_func = EnumWindowsProc(callback)
    user32.EnumWindows(enum_func, 0)

    if result:
        return result[0]
    return None


@mcp.tool()
async def cv_wait_for_window(title_pattern: str, timeout: float = 10.0) -> dict:
    """Wait for a window with a title matching a regex pattern to appear.

    Polls every 250ms until a matching window is found or timeout is reached.

    Args:
        title_pattern: Regex pattern to match against window titles (case-insensitive).
        timeout: Maximum time to wait in seconds (capped at 60s).

    Returns:
        Structured result with found=True/False and window details if found.
    """
    # Validate pattern
    try:
        compiled = re.compile(title_pattern, re.IGNORECASE)
    except re.error as exc:
        return make_error(INVALID_INPUT, f"Invalid regex pattern: {exc}")

    # Cap timeout
    timeout = min(timeout, config.MAX_WAIT_TIMEOUT)
    if timeout <= 0:
        return make_error(INVALID_INPUT, "Timeout must be positive")

    poll_interval = 0.25  # 250ms
    elapsed = 0.0

    while elapsed < timeout:
        match = _enum_windows_by_title(compiled)
        if match is not None:
            hwnd, title = match
            return make_success(found=True, hwnd=hwnd, title=title)
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return make_success(found=False, message=f"No window matching '{title_pattern}' found within {timeout}s")


@mcp.tool()
async def cv_wait(seconds: float) -> dict:
    """Wait for a specified number of seconds.

    Simple async delay for pacing automation steps.

    Args:
        seconds: Number of seconds to wait (capped at 30s).

    Returns:
        Structured result confirming the wait duration.
    """
    if seconds <= 0:
        return make_error(INVALID_INPUT, "Wait duration must be positive")

    seconds = min(seconds, config.MAX_SIMPLE_WAIT)
    await asyncio.sleep(seconds)
    return make_success(waited=seconds)
