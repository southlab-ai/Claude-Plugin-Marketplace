"""Tests for cv_scroll tool (F3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


HWND = 12345


# ---------------------------------------------------------------------------
# Patches applied to every test — security + win32 side effects disabled
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_security_and_win32():
    """Patch security gates and win32 calls so tests run without a real desktop."""
    with (
        patch("src.tools.scroll.validate_hwnd_range"),
        patch("src.tools.scroll.validate_hwnd_fresh", return_value=True),
        patch("src.tools.scroll.check_restricted"),
        patch("src.tools.scroll.check_rate_limit"),
        patch("src.tools.scroll.guard_dry_run", return_value=None),
        patch("src.tools.scroll.log_action"),
        patch("src.tools.scroll.focus_window", return_value=True),
        patch("src.tools.scroll._get_hwnd_process_name", return_value="notepad"),
        patch("src.tools.scroll._capture_post_action", return_value="/tmp/scroll.png"),
        patch("src.tools.scroll._build_window_state", return_value={"hwnd": HWND, "title": "Test", "is_foreground": True, "rect": {}}),
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
        patch("src.tools.scroll.normalize_for_sendinput", return_value=(32768, 32768)),
        patch("src.tools.scroll.validate_coordinates", return_value=True),
        patch("src.tools.scroll.to_screen_absolute", return_value=(300, 400)),
        patch("src.tools.scroll.win32gui") as mock_win32gui,
    ):
        mock_win32gui.GetWindowRect.return_value = (100, 200, 500, 600)
        yield


# ===========================================================================
# Direction tests
# ===========================================================================


def test_scroll_down_success():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="down")

    assert result["success"] is True
    mock_scroll.assert_called_once()
    args = mock_scroll.call_args
    assert args[0][2] == "down"  # direction argument


def test_scroll_up_success():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="up")

    assert result["success"] is True
    mock_scroll.assert_called_once()
    args = mock_scroll.call_args
    assert args[0][2] == "up"


def test_scroll_left_uses_direction():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="left")

    assert result["success"] is True
    args = mock_scroll.call_args
    assert args[0][2] == "left"


def test_scroll_right_uses_direction():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="right")

    assert result["success"] is True
    args = mock_scroll.call_args
    assert args[0][2] == "right"


def test_scroll_invalid_direction():
    from src.tools.scroll import cv_scroll

    result = cv_scroll(hwnd=HWND, direction="diagonal")

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


# ===========================================================================
# Amount clamping
# ===========================================================================


def test_scroll_amount_clamped_min():
    """amount=0 should be clamped to 1."""
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="down", amount=0)

    assert result["success"] is True
    args = mock_scroll.call_args
    assert args[0][3] == 1  # amount clamped to 1


def test_scroll_amount_clamped_max():
    """amount=25 should be clamped to 20."""
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=True) as mock_scroll:
        result = cv_scroll(hwnd=HWND, direction="down", amount=25)

    assert result["success"] is True
    args = mock_scroll.call_args
    assert args[0][3] == 20  # amount clamped to 20


# ===========================================================================
# Security gate
# ===========================================================================


def test_scroll_security_gate_full():
    """Verify all security functions are called."""
    from src.tools.scroll import cv_scroll

    with (
        patch("src.tools.scroll.validate_hwnd_range") as mock_vhr,
        patch("src.tools.scroll.validate_hwnd_fresh", return_value=True) as mock_vhf,
        patch("src.tools.scroll._get_hwnd_process_name", return_value="notepad") as mock_gpn,
        patch("src.tools.scroll.check_restricted") as mock_cr,
        patch("src.tools.scroll.check_rate_limit") as mock_rl,
        patch("src.tools.scroll.guard_dry_run", return_value=None) as mock_dry,
        patch("src.tools.scroll.log_action") as mock_log,
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        cv_scroll(hwnd=HWND, direction="down")

    mock_vhr.assert_called_once_with(HWND)
    mock_vhf.assert_called_once_with(HWND)
    mock_gpn.assert_called_once_with(HWND)
    mock_cr.assert_called_once_with("notepad")
    mock_rl.assert_called_once()
    mock_dry.assert_called_once()
    mock_log.assert_called()


# ===========================================================================
# Coordinate handling
# ===========================================================================


def test_scroll_default_coords_window_center():
    """No x/y provided — defaults to window center."""
    from src.tools.scroll import cv_scroll

    with (
        patch("src.tools.scroll.win32gui") as mock_win32gui,
        patch("src.tools.scroll.normalize_for_sendinput", return_value=(32768, 32768)) as mock_norm,
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        mock_win32gui.GetWindowRect.return_value = (100, 200, 500, 600)
        cv_scroll(hwnd=HWND, direction="down")

    # Center of (100,200)-(500,600) = (300, 400)
    mock_norm.assert_called_once_with(300, 400)


def test_scroll_custom_coords():
    """x=50, y=50 provided — to_screen_absolute called."""
    from src.tools.scroll import cv_scroll

    with (
        patch("src.tools.scroll.to_screen_absolute", return_value=(150, 250)) as mock_tsa,
        patch("src.tools.scroll.normalize_for_sendinput", return_value=(10000, 20000)),
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        cv_scroll(hwnd=HWND, direction="down", x=50, y=50)

    mock_tsa.assert_called_once_with(50, 50, HWND)


# ===========================================================================
# Screenshot and window state
# ===========================================================================


def test_scroll_screenshot_in_response():
    from src.tools.scroll import cv_scroll

    with (
        patch("src.tools.scroll._capture_post_action", return_value="/tmp/scroll.png"),
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        result = cv_scroll(hwnd=HWND, direction="down", screenshot=True)

    assert result["success"] is True
    assert result["image_path"] == "/tmp/scroll.png"


def test_scroll_screenshot_false_no_capture():
    from src.tools.scroll import cv_scroll

    with (
        patch("src.tools.scroll._capture_post_action") as mock_cap,
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        result = cv_scroll(hwnd=HWND, direction="down", screenshot=False)

    assert result["success"] is True
    assert "image_path" not in result
    mock_cap.assert_not_called()


def test_scroll_window_state_in_response():
    from src.tools.scroll import cv_scroll

    ws_dict = {"hwnd": HWND, "title": "Test", "is_foreground": True, "rect": {}}
    with (
        patch("src.tools.scroll._build_window_state", return_value=ws_dict),
        patch("src.tools.scroll.send_mouse_scroll", return_value=True),
    ):
        result = cv_scroll(hwnd=HWND, direction="down")

    assert result["success"] is True
    assert result["window_state"] == ws_dict


# ===========================================================================
# Error cases
# ===========================================================================


def test_scroll_empty_process_name_denied():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll._get_hwnd_process_name", return_value=""):
        result = cv_scroll(hwnd=HWND, direction="down")

    assert result["success"] is False
    assert result["error"]["code"] == "ACCESS_DENIED"


def test_scroll_sendinput_failure():
    from src.tools.scroll import cv_scroll

    with patch("src.tools.scroll.send_mouse_scroll", return_value=False):
        result = cv_scroll(hwnd=HWND, direction="down")

    assert result["success"] is False
    assert result["error"]["code"] == "INPUT_FAILED"
