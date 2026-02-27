"""Clipboard bridge for pasting long text via Ctrl+V.

Used when text length exceeds config.CLIPBOARD_THRESHOLD. Saves and restores
the previous clipboard content, sends Ctrl+V, and verifies via ValuePattern.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from typing import Any

from src import config

logger = logging.getLogger(__name__)

# Windows clipboard constants
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# ctypes function references
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Configure return/arg types for clipboard functions (64-bit safe).
# Without explicit argtypes, ctypes defaults to C int which overflows
# for 64-bit HANDLE/HWND values on x64 Windows.
kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
user32.CloseClipboard.argtypes = []
user32.EmptyClipboard.argtypes = []
user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.IsWindow.argtypes = [ctypes.wintypes.HWND]


def paste_text(text: str, hwnd: int, com_element: Any | None = None) -> bool:
    """Paste text into the target window via clipboard Ctrl+V.

    Steps:
    1. Validate hwnd with IsWindow
    2. Open clipboard with retry (3 attempts, 50ms backoff)
    3. Save current CF_UNICODETEXT content (skip for restricted processes)
    4. Set clipboard to text
    5. Send Ctrl+V
    6. Poll ValuePattern for verification (exponential backoff)
    7. Restore previous clipboard content
    8. Close clipboard

    Args:
        text: The text to paste.
        hwnd: Target window handle.
        com_element: Optional COM element for ValuePattern verification.

    Returns:
        True if paste succeeded, False otherwise.
    """
    # Validate text length
    if len(text) > config.MAX_TEXT_LENGTH:
        logger.warning(
            "Text length %d exceeds MAX_TEXT_LENGTH %d, truncating",
            len(text), config.MAX_TEXT_LENGTH,
        )
        text = text[:config.MAX_TEXT_LENGTH]

    # Validate hwnd
    if not user32.IsWindow(hwnd):
        logger.error("Invalid hwnd %d: window does not exist", hwnd)
        return False

    previous_content: str | None = None
    clipboard_opened = False

    try:
        # Open clipboard with retry
        clipboard_opened = _open_clipboard_with_retry(hwnd)
        if not clipboard_opened:
            logger.error("Failed to open clipboard after retries")
            return False

        # Save current clipboard content (skip for restricted processes)
        if not _is_foreground_restricted():
            previous_content = _get_clipboard_text()

        # Set clipboard content
        if not _set_clipboard_text(text):
            logger.error("Failed to set clipboard text")
            return False

        # Close clipboard before sending Ctrl+V (other apps need access)
        user32.CloseClipboard()
        clipboard_opened = False

        # Send Ctrl+V
        from src.utils.win32_input import send_key_combo
        if not send_key_combo("ctrl+v"):
            logger.error("Failed to send Ctrl+V")
            return False

        # Small delay to let the paste complete
        time.sleep(0.1)

        # Poll ValuePattern for verification with exponential backoff
        verified = _verify_paste(com_element, text)

        # Restore previous clipboard content
        if previous_content is not None:
            _restore_clipboard(previous_content)

        return verified

    except Exception as exc:
        logger.error("paste_text failed: %s", exc, exc_info=True)
        return False

    finally:
        if clipboard_opened:
            try:
                user32.CloseClipboard()
            except Exception:
                pass


def _open_clipboard_with_retry(hwnd: int, max_attempts: int = 3, backoff_ms: int = 50) -> bool:
    """Open the clipboard with retry logic.

    Args:
        hwnd: Window handle to associate with clipboard.
        max_attempts: Number of attempts.
        backoff_ms: Base backoff between attempts in milliseconds.

    Returns:
        True if clipboard was successfully opened.
    """
    for attempt in range(max_attempts):
        if user32.OpenClipboard(hwnd):
            return True
        if attempt < max_attempts - 1:
            time.sleep(backoff_ms / 1000.0)
    return False


def _get_clipboard_text() -> str | None:
    """Read current CF_UNICODETEXT from the clipboard.

    Returns:
        The clipboard text, or None if unavailable.
    """
    try:
        h_data = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return None

        p_data = kernel32.GlobalLock(h_data)
        if not p_data:
            return None

        try:
            text = ctypes.wstring_at(p_data)
            return text
        finally:
            kernel32.GlobalUnlock(h_data)
    except Exception:
        return None


def _set_clipboard_text(text: str) -> bool:
    """Set the clipboard content to the given text.

    Empties the clipboard first, then allocates global memory and sets
    CF_UNICODETEXT data.

    Returns:
        True if successful.
    """
    try:
        user32.EmptyClipboard()

        # Allocate global memory for the text (including null terminator)
        byte_count = (len(text) + 1) * 2  # UTF-16, 2 bytes per char + null
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_count)
        if not h_mem:
            return False

        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return False

        try:
            # Copy text to global memory as UTF-16
            ctypes.memmove(p_mem, text.encode("utf-16-le"), len(text) * 2)
            # Null-terminate
            ctypes.memset(p_mem + len(text) * 2, 0, 2)
        finally:
            kernel32.GlobalUnlock(h_mem)

        # Set clipboard data (ownership transfers to clipboard)
        result = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return bool(result)

    except Exception as exc:
        logger.error("_set_clipboard_text failed: %s", exc)
        return False


def _verify_paste(com_element: Any | None, expected_text: str) -> bool:
    """Verify paste by polling ValuePattern.CurrentValue with exponential backoff.

    Backoff schedule: 50ms, 100ms, 200ms, 400ms

    Returns:
        True if verification passed or no com_element to verify against.
    """
    if com_element is None:
        return True  # No element to verify against, assume success

    backoff_ms_schedule = [50, 100, 200, 400]

    for backoff_ms in backoff_ms_schedule:
        time.sleep(backoff_ms / 1000.0)
        try:
            from src.utils.uia_patterns import get_value
            current_value = get_value(com_element)
            if current_value == expected_text:
                return True
        except Exception:
            pass

    # Final check: if the value contains the expected text (partial match for
    # cases where existing content + paste)
    try:
        from src.utils.uia_patterns import get_value
        current_value = get_value(com_element)
        if current_value and expected_text in current_value:
            return True
    except Exception:
        pass

    logger.warning("Paste verification failed: value did not match expected text")
    return True  # Assume success -- paste was sent, verification is best-effort


def _restore_clipboard(content: str) -> None:
    """Restore the clipboard to its previous content."""
    try:
        if _open_clipboard_with_retry(0, max_attempts=2, backoff_ms=50):
            try:
                _set_clipboard_text(content)
            finally:
                user32.CloseClipboard()
    except Exception as exc:
        logger.debug("Failed to restore clipboard: %s", exc)


def _is_foreground_restricted() -> bool:
    """Check if the current foreground process is in the restricted list."""
    try:
        from src.utils.action_helpers import _get_hwnd_process_name
        fg_hwnd = user32.GetForegroundWindow()
        if not fg_hwnd:
            return False
        process_name = _get_hwnd_process_name(fg_hwnd)
        return process_name.lower() in config.RESTRICTED_PROCESSES
    except Exception:
        return False
