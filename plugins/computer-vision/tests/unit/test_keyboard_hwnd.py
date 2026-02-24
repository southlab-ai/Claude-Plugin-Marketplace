"""Tests for atomic keyboard operations with hwnd parameter (F1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


HWND = 12345
OTHER_HWND = 99999


# ---------------------------------------------------------------------------
# Patches applied to every test — security + win32 side effects disabled
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_security_and_win32():
    """Patch security gates and win32 calls so tests run without a real desktop."""
    with (
        patch("src.tools.input_keyboard.validate_hwnd_range"),
        patch("src.tools.input_keyboard.validate_hwnd_fresh", return_value=True),
        patch("src.tools.input_keyboard.check_restricted"),
        patch("src.tools.input_keyboard.check_rate_limit"),
        patch("src.tools.input_keyboard.guard_dry_run", return_value=None),
        patch("src.tools.input_keyboard.log_action"),
        patch("src.tools.input_keyboard.type_unicode_string", return_value=True),
        patch("src.tools.input_keyboard.send_key_combo", return_value=True),
        patch("src.tools.input_keyboard.focus_window", return_value=True),
        patch("src.tools.input_keyboard._get_hwnd_process_name", return_value="notepad"),
        patch("src.tools.input_keyboard._capture_post_action", return_value="/tmp/img.png"),
        patch("src.tools.input_keyboard._build_window_state", return_value={"hwnd": HWND, "title": "Test", "is_foreground": True, "rect": {}}),
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard.time"),
    ):
        # Default: GetForegroundWindow returns the target hwnd (focus succeeds)
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        yield


# ===========================================================================
# cv_type_text — no hwnd (backward compat)
# ===========================================================================


def test_type_text_hwnd_none_preserves_v150_behavior():
    """Call cv_type_text("hello") with no hwnd — old behavior preserved."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.check_rate_limit") as mock_rl,
        patch("src.tools.input_keyboard.guard_dry_run", return_value=None) as mock_dry,
        patch("src.tools.input_keyboard.type_unicode_string", return_value=True) as mock_type,
        patch("src.tools.input_keyboard.validate_hwnd_range") as mock_vhr,
        patch("src.tools.input_keyboard._capture_post_action") as mock_cap,
        patch("src.tools.input_keyboard._build_window_state") as mock_ws,
    ):
        result = cv_type_text("hello")

        assert result["success"] is True
        mock_rl.assert_called()
        mock_dry.assert_called()
        mock_type.assert_called_once_with("hello")
        # hwnd-specific calls should NOT happen
        mock_vhr.assert_not_called()
        # No image_path or window_state in response
        assert "image_path" not in result
        assert "window_state" not in result


# ===========================================================================
# cv_type_text — hwnd path
# ===========================================================================


def test_type_text_hwnd_triggers_security_gate():
    """Call with hwnd=12345 — verify security gate calls in order."""
    from src.tools.input_keyboard import cv_type_text

    call_order = []

    with (
        patch("src.tools.input_keyboard.validate_hwnd_range", side_effect=lambda h: call_order.append("validate_hwnd_range")),
        patch("src.tools.input_keyboard.validate_hwnd_fresh", side_effect=lambda h: (call_order.append("validate_hwnd_fresh"), True)[-1]),
        patch("src.tools.input_keyboard._get_hwnd_process_name", side_effect=lambda h: (call_order.append("_get_hwnd_process_name"), "notepad")[-1]),
        patch("src.tools.input_keyboard.check_restricted", side_effect=lambda p: call_order.append("check_restricted")),
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        cv_type_text("hello", hwnd=HWND)

    assert call_order[:4] == [
        "validate_hwnd_range",
        "validate_hwnd_fresh",
        "_get_hwnd_process_name",
        "check_restricted",
    ]


def test_type_text_hwnd_focus_success_first_try():
    """Focus succeeds on first try — type_unicode_string called, success returned."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard.type_unicode_string", return_value=True) as mock_type,
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is True
    mock_type.assert_called_once_with("hello")


def test_type_text_hwnd_focus_retry_then_success():
    """First focus attempt fails, second succeeds."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard.focus_window") as mock_focus,
        patch("src.tools.input_keyboard.time") as mock_time,
        patch("src.tools.input_keyboard.type_unicode_string", return_value=True) as mock_type,
    ):
        # First call returns wrong hwnd, second returns correct
        mock_ctypes.windll.user32.GetForegroundWindow.side_effect = [OTHER_HWND, HWND]
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is True
    assert mock_focus.call_count == 2
    mock_time.sleep.assert_called()


def test_type_text_hwnd_focus_exhausted_returns_error():
    """Focus never succeeds after MAX_RETRIES attempts — error returned."""
    from src.tools.input_keyboard import cv_type_text

    with patch("src.tools.input_keyboard.ctypes") as mock_ctypes:
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is False
    assert result["error"]["code"] == "INPUT_FAILED"


def test_type_text_hwnd_screenshot_in_response():
    """When screenshot=True and capture succeeds, image_path is in response."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard._capture_post_action", return_value="/tmp/img.png") as mock_cap,
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_type_text("hello", hwnd=HWND, screenshot=True)

    assert result["success"] is True
    assert result["image_path"] == "/tmp/img.png"
    mock_cap.assert_called_once()


def test_type_text_hwnd_screenshot_false_no_capture():
    """When screenshot=False, _capture_post_action is NOT called."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard._capture_post_action") as mock_cap,
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_type_text("hello", hwnd=HWND, screenshot=False)

    assert result["success"] is True
    assert "image_path" not in result
    mock_cap.assert_not_called()


def test_type_text_hwnd_window_state_in_response():
    """window_state dict should be present in response when hwnd is provided."""
    from src.tools.input_keyboard import cv_type_text

    ws_dict = {"hwnd": HWND, "title": "Test", "is_foreground": True, "rect": {}}
    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard._build_window_state", return_value=ws_dict),
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is True
    assert result["window_state"] == ws_dict


def test_type_text_hwnd_empty_process_name_denied():
    """If _get_hwnd_process_name returns '', ACCESS_DENIED error returned."""
    from src.tools.input_keyboard import cv_type_text

    with patch("src.tools.input_keyboard._get_hwnd_process_name", return_value=""):
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is False
    assert result["error"]["code"] == "ACCESS_DENIED"


def test_type_text_hwnd_rate_limit_per_retry():
    """check_rate_limit should be called inside the retry loop (at least once on success)."""
    from src.tools.input_keyboard import cv_type_text

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard.check_rate_limit") as mock_rl,
        patch("src.tools.input_keyboard.type_unicode_string", return_value=True),
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        cv_type_text("hello", hwnd=HWND)

    mock_rl.assert_called()


def test_type_text_hwnd_invalid_hwnd_range():
    """validate_hwnd_range raises ValueError — error returned."""
    from src.tools.input_keyboard import cv_type_text

    with patch("src.tools.input_keyboard.validate_hwnd_range", side_effect=ValueError("Invalid HWND: 0")):
        result = cv_type_text("hello", hwnd=0)

    assert result["success"] is False


def test_type_text_hwnd_stale_window():
    """validate_hwnd_fresh returns False — error returned."""
    from src.tools.input_keyboard import cv_type_text

    with patch("src.tools.input_keyboard.validate_hwnd_fresh", return_value=False):
        result = cv_type_text("hello", hwnd=HWND)

    assert result["success"] is False


# ===========================================================================
# cv_send_keys — hwnd path
# ===========================================================================


def test_send_keys_hwnd_focus_and_screenshot():
    """cv_send_keys with hwnd — focus_window called, send_key_combo called, screenshot captured."""
    from src.tools.input_keyboard import cv_send_keys

    with (
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
        patch("src.tools.input_keyboard.focus_window") as mock_focus,
        patch("src.tools.input_keyboard.send_key_combo", return_value=True) as mock_combo,
        patch("src.tools.input_keyboard._capture_post_action", return_value="/tmp/keys.png"),
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_send_keys("ctrl+c", hwnd=HWND)

    assert result["success"] is True
    mock_focus.assert_called()
    mock_combo.assert_called_once_with("ctrl+c")
    assert result["image_path"] == "/tmp/keys.png"


def test_send_keys_hwnd_none_preserves_v150():
    """cv_send_keys("ctrl+c") with no hwnd — old behavior preserved."""
    from src.tools.input_keyboard import cv_send_keys

    with (
        patch("src.tools.input_keyboard.check_rate_limit") as mock_rl,
        patch("src.tools.input_keyboard.guard_dry_run", return_value=None),
        patch("src.tools.input_keyboard.send_key_combo", return_value=True) as mock_combo,
        patch("src.tools.input_keyboard.validate_hwnd_range") as mock_vhr,
        patch("src.tools.input_keyboard._capture_post_action") as mock_cap,
    ):
        result = cv_send_keys("ctrl+c")

    assert result["success"] is True
    mock_rl.assert_called()
    mock_combo.assert_called_once_with("ctrl+c")
    mock_vhr.assert_not_called()
    assert "image_path" not in result
    assert "window_state" not in result


def test_type_text_hwnd_dry_run():
    """guard_dry_run returns a dict — that dict is returned directly."""
    from src.tools.input_keyboard import cv_type_text

    dry_result = {"success": False, "error": {"code": "DRY_RUN", "message": "dry run"}}
    with (
        patch("src.tools.input_keyboard.guard_dry_run", return_value=dry_result),
        patch("src.tools.input_keyboard.ctypes") as mock_ctypes,
    ):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        result = cv_type_text("hello", hwnd=HWND)

    assert result == dry_result
