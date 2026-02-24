"""pywin32 wrappers for window enumeration, focus, and management."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from pathlib import Path
from typing import Any

import win32api
import win32con
import win32gui
import win32process

from src.errors import WindowNotFoundError
from src.models import Rect, WindowInfo

logger = logging.getLogger(__name__)

MONITOR_DEFAULTTONEAREST = 2


def _get_process_name(pid: int) -> str:
    """Get the executable name (without extension) for a given PID."""
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False,
            pid,
        )
        try:
            exe = win32process.GetModuleFileNameEx(handle, 0)
            return Path(exe).stem.lower()
        finally:
            win32api.CloseHandle(handle)
    except Exception:
        return ""


def _get_monitor_index(hwnd: int) -> int:
    """Get the 1-based monitor index for the monitor containing a window."""
    try:
        hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        monitors = win32api.EnumDisplayMonitors(None, None)
        for i, (hm, _hdc, _rect) in enumerate(monitors):
            if int(hm) == hmon:
                return i
        return 0
    except Exception:
        return 0


def _build_window_info(hwnd: int) -> WindowInfo | None:
    """Build a WindowInfo from a window handle. Returns None if info cannot be gathered."""
    try:
        title = win32gui.GetWindowText(hwnd)
        rect_tuple = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        process_name = _get_process_name(pid)
        monitor_index = _get_monitor_index(hwnd)

        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]
        is_minimized = show_cmd == win32con.SW_SHOWMINIMIZED
        is_maximized = show_cmd == win32con.SW_SHOWMAXIMIZED

        foreground_hwnd = win32gui.GetForegroundWindow()

        return WindowInfo(
            hwnd=hwnd,
            title=title,
            process_name=process_name,
            class_name=class_name,
            pid=pid,
            rect=Rect(
                x=rect_tuple[0],
                y=rect_tuple[1],
                width=rect_tuple[2] - rect_tuple[0],
                height=rect_tuple[3] - rect_tuple[1],
            ),
            monitor_index=monitor_index,
            is_minimized=is_minimized,
            is_maximized=is_maximized,
            is_foreground=(hwnd == foreground_hwnd),
        )
    except Exception as exc:
        logger.debug("Failed to get info for HWND %s: %s", hwnd, exc)
        return None


def enum_windows(include_children: bool = False) -> list[WindowInfo]:
    """Enumerate all visible top-level windows.

    Args:
        include_children: If True, also enumerate child windows.

    Returns:
        List of WindowInfo for each visible window.
    """
    results: list[WindowInfo] = []

    def _callback(hwnd: int, _extra: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True

        info = _build_window_info(hwnd)
        if info is not None:
            results.append(info)

            if include_children:
                _enum_child_windows(hwnd, results)

        return True

    win32gui.EnumWindows(_callback, None)
    return results


def _enum_child_windows(parent_hwnd: int, results: list[WindowInfo]) -> None:
    """Enumerate visible child windows of a parent."""

    def _child_callback(hwnd: int, _extra: Any) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        info = _build_window_info(hwnd)
        if info is not None:
            results.append(info)
        return True

    try:
        win32gui.EnumChildWindows(parent_hwnd, _child_callback, None)
    except Exception as exc:
        logger.debug("Failed to enumerate children of HWND %s: %s", parent_hwnd, exc)


def get_window_info(hwnd: int) -> WindowInfo:
    """Get detailed information about a specific window.

    Args:
        hwnd: Window handle.

    Returns:
        WindowInfo for the window.

    Raises:
        WindowNotFoundError: If the window is invalid.
    """
    if not is_window_valid(hwnd):
        raise WindowNotFoundError(hwnd)

    info = _build_window_info(hwnd)
    if info is None:
        raise WindowNotFoundError(hwnd)
    return info


def _is_focused(hwnd: int) -> bool:
    """Check if the given window is currently the foreground window."""
    return ctypes.windll.user32.GetForegroundWindow() == hwnd


def _strategy_direct(hwnd: int) -> bool:
    """Strategy 1: Direct SetForegroundWindow call."""
    try:
        win32gui.SetForegroundWindow(hwnd)
        return _is_focused(hwnd)
    except Exception as exc:
        logger.debug("Direct focus failed for HWND %s: %s", hwnd, exc)
        return False


def _strategy_alt_trick(hwnd: int) -> bool:
    """Strategy 2: Inject ALT key via SendInput to unlock foreground, then SetForegroundWindow.

    Uses paired keydown+keyup in a single SendInput call to prevent stuck keys.
    """
    try:
        # Define INPUT structures for SendInput
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        VK_MENU = 0x12

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.wintypes.WORD),
                ("wScan", ctypes.wintypes.WORD),
                ("dwFlags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            class _INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _fields_ = [
                ("type", ctypes.wintypes.DWORD),
                ("union", _INPUT_UNION),
            ]

        # Build paired keydown + keyup inputs
        inputs = (INPUT * 2)()

        # ALT keydown
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].union.ki.wVk = VK_MENU
        inputs[0].union.ki.dwFlags = 0

        # ALT keyup
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].union.ki.wVk = VK_MENU
        inputs[1].union.ki.dwFlags = KEYEVENTF_KEYUP

        ctypes.windll.user32.SendInput(2, ctypes.pointer(inputs[0]), ctypes.sizeof(INPUT))

        win32gui.SetForegroundWindow(hwnd)
        return _is_focused(hwnd)
    except Exception as exc:
        logger.debug("ALT trick focus failed for HWND %s: %s", hwnd, exc)
        return False


def _strategy_attach_thread(hwnd: int) -> bool:
    """Strategy 3: AttachThreadInput + BringWindowToTop + SetForegroundWindow."""
    fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
    if fg_hwnd == 0:
        fg_hwnd = hwnd
    fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
    target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
    attached = False
    try:
        if fg_thread != target_thread:
            ctypes.windll.user32.AttachThreadInput(target_thread, fg_thread, True)
            attached = True
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        return _is_focused(hwnd)
    except Exception as exc:
        logger.debug("AttachThreadInput focus failed for HWND %s: %s", hwnd, exc)
        return False
    finally:
        if attached:
            try:
                ctypes.windll.user32.AttachThreadInput(target_thread, fg_thread, False)
            except Exception:
                pass


def _strategy_spi_bypass(hwnd: int) -> bool:
    """Strategy 4: Temporarily zero the foreground lock timeout via SystemParametersInfoW."""
    SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
    SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
    SPIF_SENDCHANGE = 0x0002

    old_timeout = ctypes.wintypes.DWORD(0)
    restored = False
    try:
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(old_timeout), 0
        )
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, None, SPIF_SENDCHANGE
        )
        win32gui.SetForegroundWindow(hwnd)
        result = _is_focused(hwnd)
        return result
    except Exception as exc:
        logger.debug("SPI bypass focus failed for HWND %s: %s", hwnd, exc)
        return False
    finally:
        try:
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETFOREGROUNDLOCKTIMEOUT, 0,
                ctypes.cast(ctypes.c_void_p(old_timeout.value), ctypes.c_void_p),
                SPIF_SENDCHANGE,
            )
            restored = True
        except Exception:
            pass
        if not restored:
            logger.debug("Failed to restore SPI foreground lock timeout")


# Ordered list of focus strategies
_FOCUS_STRATEGIES = [
    _strategy_direct,
    _strategy_alt_trick,
    _strategy_attach_thread,
    _strategy_spi_bypass,
]

_FOCUS_MAX_ATTEMPTS = 6
_FOCUS_RETRY_DELAY = 0.05  # 50ms


def focus_window(hwnd: int) -> bool:
    """Bring a window to the foreground using a 4-strategy escalation.

    Restores minimized windows before focusing. Tries up to 6 attempts
    cycling through strategies: direct, ALT trick, AttachThreadInput, SPI bypass.

    Args:
        hwnd: Window handle to focus.

    Returns:
        True if the window was successfully brought to the foreground.
    """
    if not is_window_valid(hwnd):
        return False

    try:
        # Restore if minimized
        if ctypes.windll.user32.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception as exc:
        logger.debug("Failed to restore minimized window HWND %s: %s", hwnd, exc)

    for attempt in range(_FOCUS_MAX_ATTEMPTS):
        strategy_index = attempt % len(_FOCUS_STRATEGIES)
        strategy = _FOCUS_STRATEGIES[strategy_index]

        try:
            if strategy(hwnd):
                return True
        except Exception as exc:
            logger.debug(
                "Focus strategy %s attempt %d failed for HWND %s: %s",
                strategy.__name__, attempt, hwnd, exc,
            )

        if attempt < _FOCUS_MAX_ATTEMPTS - 1:
            time.sleep(_FOCUS_RETRY_DELAY)

    logger.warning("All focus strategies exhausted for HWND %s after %d attempts", hwnd, _FOCUS_MAX_ATTEMPTS)
    return False


def move_window(hwnd: int, x: int, y: int, width: int, height: int) -> Rect:
    """Move and resize a window.

    Args:
        hwnd: Window handle.
        x: New left position.
        y: New top position.
        width: New width.
        height: New height.

    Returns:
        The new Rect after moving.
    """
    if not is_window_valid(hwnd):
        raise WindowNotFoundError(hwnd)

    win32gui.MoveWindow(hwnd, x, y, width, height, True)

    # Read back the actual position
    rect_tuple = win32gui.GetWindowRect(hwnd)
    return Rect(
        x=rect_tuple[0],
        y=rect_tuple[1],
        width=rect_tuple[2] - rect_tuple[0],
        height=rect_tuple[3] - rect_tuple[1],
    )


def is_window_valid(hwnd: int) -> bool:
    """Check if a window handle is still valid."""
    return bool(ctypes.windll.user32.IsWindow(hwnd))
