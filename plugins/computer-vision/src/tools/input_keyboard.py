"""MCP tools for keyboard input: text typing and key combinations."""

from __future__ import annotations

import ctypes
import logging
import time

from src.server import mcp
from src import config
from src.errors import make_error, make_success, INPUT_FAILED, INVALID_INPUT, ACCESS_DENIED
from src.utils.security import (
    validate_hwnd_range,
    validate_hwnd_fresh,
    check_restricted,
    check_rate_limit,
    guard_dry_run,
    log_action,
)
from src.utils.win32_input import type_unicode_string, send_key_combo
from src.utils.win32_window import focus_window
from src.utils.action_helpers import _get_hwnd_process_name, _capture_post_action, _build_window_state

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@mcp.tool()
def cv_type_text(
    text: str,
    hwnd: int | None = None,
    screenshot: bool = True,
    screenshot_delay_ms: int = 150,
) -> dict:
    """Type a string of text at the current cursor position using Unicode input.

    Args:
        text: The text to type. Maximum length is controlled by CV_MAX_TEXT_LENGTH (default 1000).
        hwnd: Optional window handle. When provided, focuses the window first and applies
              full security validation (HWND freshness, process restriction, rate limiting).
        screenshot: Whether to capture a screenshot after typing (default True). Only used when hwnd is provided.
        screenshot_delay_ms: Delay in ms before screenshot capture (default 150). Only used when hwnd is provided.
    """
    try:
        if not text:
            return make_error(INVALID_INPUT, "Text must not be empty.")

        if len(text) > config.MAX_TEXT_LENGTH:
            return make_error(
                INVALID_INPUT,
                f"Text length {len(text)} exceeds maximum {config.MAX_TEXT_LENGTH}.",
            )

        if hwnd is not None:
            # --- HWND-targeted path with full security gate ---
            validate_hwnd_range(hwnd)
            if not validate_hwnd_fresh(hwnd):
                return make_error(INPUT_FAILED, f"HWND {hwnd} is no longer valid.")

            process_name = _get_hwnd_process_name(hwnd)
            if not process_name:
                return make_error(ACCESS_DENIED, "Cannot determine process for HWND")

            check_restricted(process_name)

            params = {"text": text, "hwnd": hwnd}
            dry = guard_dry_run("cv_type_text", params)
            if dry is not None:
                return dry

            log_action("cv_type_text", params, "start")

            # Atomic focus + type retry loop
            ok = False
            for attempt in range(MAX_RETRIES):
                focus_window(hwnd)
                if ctypes.windll.user32.GetForegroundWindow() != hwnd:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(0.05)
                        continue
                    return make_error(INPUT_FAILED, f"Could not acquire focus on HWND {hwnd} after {MAX_RETRIES} attempts")
                check_rate_limit()
                ok = type_unicode_string(text)
                if ok:
                    break

            log_action("cv_type_text", params, "ok" if ok else "fail")

            if not ok:
                return make_error(INPUT_FAILED, "SendInput failed for text typing.")

            result = make_success(action="type_text", length=len(text))
            if screenshot:
                image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
                if image_path:
                    result["image_path"] = image_path
            window_state = _build_window_state(hwnd)
            if window_state:
                result["window_state"] = window_state
            return result

        else:
            # --- Backward-compatible path (no hwnd) ---
            check_rate_limit()

            params = {"text": text}
            dry = guard_dry_run("cv_type_text", params)
            if dry is not None:
                return dry

            log_action("cv_type_text", params, "start")

            ok = type_unicode_string(text)
            log_action("cv_type_text", params, "ok" if ok else "fail")

            if not ok:
                return make_error(INPUT_FAILED, "SendInput failed for text typing.")

            return make_success(action="type_text", length=len(text))

    except Exception as e:
        return make_error(INPUT_FAILED, str(e))


@mcp.tool()
def cv_send_keys(
    keys: str,
    hwnd: int | None = None,
    screenshot: bool = True,
    screenshot_delay_ms: int = 150,
) -> dict:
    """Send a keyboard shortcut or key combination (e.g., "ctrl+c", "alt+tab", "ctrl+shift+s").

    Args:
        keys: Key combination string with parts separated by "+".
              Supported modifiers: ctrl, shift, alt, win/meta/cmd.
              Supported keys: a-z, 0-9, f1-f12, enter, tab, escape, backspace, delete,
              space, up, down, left, right, home, end, pageup, pagedown, insert.
        hwnd: Optional window handle. When provided, focuses the window first and applies
              full security validation (HWND freshness, process restriction, rate limiting).
        screenshot: Whether to capture a screenshot after sending keys (default True). Only used when hwnd is provided.
        screenshot_delay_ms: Delay in ms before screenshot capture (default 150). Only used when hwnd is provided.
    """
    try:
        if not keys or not keys.strip():
            return make_error(INVALID_INPUT, "Keys must not be empty.")

        if hwnd is not None:
            # --- HWND-targeted path with full security gate ---
            validate_hwnd_range(hwnd)
            if not validate_hwnd_fresh(hwnd):
                return make_error(INPUT_FAILED, f"HWND {hwnd} is no longer valid.")

            process_name = _get_hwnd_process_name(hwnd)
            if not process_name:
                return make_error(ACCESS_DENIED, "Cannot determine process for HWND")

            check_restricted(process_name)

            params = {"keys": keys, "hwnd": hwnd}
            dry = guard_dry_run("cv_send_keys", params)
            if dry is not None:
                return dry

            log_action("cv_send_keys", params, "start")

            # Atomic focus + send retry loop
            ok = False
            for attempt in range(MAX_RETRIES):
                focus_window(hwnd)
                if ctypes.windll.user32.GetForegroundWindow() != hwnd:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(0.05)
                        continue
                    return make_error(INPUT_FAILED, f"Could not acquire focus on HWND {hwnd} after {MAX_RETRIES} attempts")
                check_rate_limit()
                ok = send_key_combo(keys)
                if ok:
                    break

            log_action("cv_send_keys", params, "ok" if ok else "fail")

            if not ok:
                return make_error(INPUT_FAILED, f"SendInput failed for key combo: {keys!r}")

            result = make_success(action="send_keys", keys=keys)
            if screenshot:
                image_path = _capture_post_action(hwnd, delay_ms=screenshot_delay_ms)
                if image_path:
                    result["image_path"] = image_path
            window_state = _build_window_state(hwnd)
            if window_state:
                result["window_state"] = window_state
            return result

        else:
            # --- Backward-compatible path (no hwnd) ---
            check_rate_limit()

            params = {"keys": keys}
            dry = guard_dry_run("cv_send_keys", params)
            if dry is not None:
                return dry

            log_action("cv_send_keys", params, "start")

            ok = send_key_combo(keys)
            log_action("cv_send_keys", params, "ok" if ok else "fail")

            if not ok:
                return make_error(INPUT_FAILED, f"SendInput failed for key combo: {keys!r}")

            return make_success(action="send_keys", keys=keys)

    except Exception as e:
        return make_error(INPUT_FAILED, str(e))
