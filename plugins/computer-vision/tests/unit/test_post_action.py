"""Tests for shared action helpers: _capture_post_action, _build_window_state, _get_hwnd_process_name."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


HWND = 12345
OTHER_HWND = 99999


# ===========================================================================
# _build_window_state
# ===========================================================================


@patch("src.utils.action_helpers.win32gui")
@patch("src.utils.action_helpers.ctypes")
def test_build_window_state_returns_correct_dict(mock_ctypes, mock_win32gui):
    mock_win32gui.GetWindowText.return_value = "My Window"
    mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
    mock_win32gui.GetWindowRect.return_value = (100, 200, 500, 600)

    from src.utils.action_helpers import _build_window_state

    result = _build_window_state(HWND)

    assert result is not None
    assert result["hwnd"] == HWND
    assert result["title"] == "My Window"
    assert "is_foreground" in result
    assert "rect" in result
    assert result["rect"]["x"] == 100
    assert result["rect"]["y"] == 200
    assert result["rect"]["width"] == 400
    assert result["rect"]["height"] == 400


@patch("src.utils.action_helpers.win32gui")
@patch("src.utils.action_helpers.ctypes")
def test_build_window_state_is_foreground_true(mock_ctypes, mock_win32gui):
    mock_win32gui.GetWindowText.return_value = "Title"
    mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
    mock_win32gui.GetWindowRect.return_value = (0, 0, 800, 600)

    from src.utils.action_helpers import _build_window_state

    result = _build_window_state(HWND)
    assert result["is_foreground"] is True


@patch("src.utils.action_helpers.win32gui")
@patch("src.utils.action_helpers.ctypes")
def test_build_window_state_is_foreground_false(mock_ctypes, mock_win32gui):
    mock_win32gui.GetWindowText.return_value = "Title"
    mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
    mock_win32gui.GetWindowRect.return_value = (0, 0, 800, 600)

    from src.utils.action_helpers import _build_window_state

    result = _build_window_state(HWND)
    assert result["is_foreground"] is False


@patch("src.utils.action_helpers.win32gui")
def test_build_window_state_invalid_hwnd_returns_none(mock_win32gui):
    mock_win32gui.GetWindowText.side_effect = Exception("invalid hwnd")

    from src.utils.action_helpers import _build_window_state

    result = _build_window_state(HWND)
    assert result is None


# ===========================================================================
# _capture_post_action
# ===========================================================================


@patch("src.utils.action_helpers.time")
@patch("src.utils.action_helpers.capture_window")
def test_capture_post_action_returns_image_path(mock_capture, mock_time):
    mock_result = MagicMock()
    mock_result.image_path = "/tmp/cv_screenshot.png"
    mock_capture.return_value = mock_result

    from src.utils.action_helpers import _capture_post_action

    path = _capture_post_action(HWND, delay_ms=150)
    assert path == "/tmp/cv_screenshot.png"


@patch("src.utils.action_helpers.time")
@patch("src.utils.action_helpers.capture_window")
def test_capture_post_action_failure_returns_none(mock_capture, mock_time):
    mock_capture.side_effect = Exception("capture failed")

    from src.utils.action_helpers import _capture_post_action

    path = _capture_post_action(HWND)
    assert path is None


@patch("src.utils.action_helpers.time")
@patch("src.utils.action_helpers.capture_window")
def test_capture_post_action_honors_delay(mock_capture, mock_time):
    mock_result = MagicMock()
    mock_result.image_path = "/tmp/img.png"
    mock_capture.return_value = mock_result

    from src.utils.action_helpers import _capture_post_action

    _capture_post_action(HWND, delay_ms=300)
    mock_time.sleep.assert_called_once_with(0.3)


@patch("src.utils.action_helpers.time")
@patch("src.utils.action_helpers.capture_window")
def test_capture_post_action_zero_delay_skips_sleep(mock_capture, mock_time):
    mock_result = MagicMock()
    mock_result.image_path = "/tmp/img.png"
    mock_capture.return_value = mock_result

    from src.utils.action_helpers import _capture_post_action

    _capture_post_action(HWND, delay_ms=0)
    mock_time.sleep.assert_not_called()


# ===========================================================================
# _get_hwnd_process_name
# ===========================================================================


@patch("src.utils.action_helpers.get_process_name_by_pid")
@patch("src.utils.action_helpers.ctypes")
def test_get_hwnd_process_name_returns_name(mock_ctypes, mock_get_name):
    # Simulate GetWindowThreadProcessId setting pid.value
    mock_pid = MagicMock()
    mock_pid.value = 1234
    mock_ctypes.c_ulong.return_value = mock_pid
    mock_get_name.return_value = "notepad"

    from src.utils.action_helpers import _get_hwnd_process_name

    result = _get_hwnd_process_name(HWND)
    assert result == "notepad"
    mock_get_name.assert_called_once_with(1234)


@patch("src.utils.action_helpers.ctypes")
def test_get_hwnd_process_name_failure_returns_empty(mock_ctypes):
    mock_ctypes.c_ulong.side_effect = Exception("fail")

    from src.utils.action_helpers import _get_hwnd_process_name

    result = _get_hwnd_process_name(HWND)
    assert result == ""


# ===========================================================================
# Screenshot cleanup throttle
# ===========================================================================


@patch("src.utils.screenshot._cleanup_old_screenshots")
def test_screenshot_cleanup_throttled(mock_cleanup):
    """Verify cleanup is called only on every 10th save_image call."""
    import src.utils.screenshot as ss
    from PIL import Image

    # Reset the counter to 0 so our test starts clean
    ss._cleanup_call_count = 0

    img = Image.new("RGB", (100, 100), color=(128, 128, 128))

    for i in range(10):
        ss.save_image(img, max_width=200)

    # Cleanup should be called exactly once (on the 10th call: count=10, 10 % 10 == 0)
    mock_cleanup.assert_called_once()
