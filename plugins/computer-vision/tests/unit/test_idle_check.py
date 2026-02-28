"""Unit tests for idle detection (src/utils/idle_check.py)."""

from __future__ import annotations

import ctypes
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.utils.idle_check import (
    is_user_idle,
    mark_synthetic_input,
    _SYNTHETIC_TOLERANCE_MS,
)
import src.utils.idle_check as idle_module


@pytest.fixture(autouse=True)
def reset_synthetic_tick():
    """Reset the synthetic input tick between tests."""
    idle_module._last_synthetic_input_tick = 0
    yield
    idle_module._last_synthetic_input_tick = 0


class TestIsUserIdle:
    def test_force_returns_true(self):
        assert is_user_idle(force=True) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    @patch("src.utils.idle_check.ctypes")
    def test_idle_above_threshold(self, mock_ctypes):
        """User has been idle longer than threshold."""
        mock_ctypes.windll.kernel32.GetTickCount.return_value = 10000
        mock_ctypes.sizeof.return_value = 8

        # Mock GetLastInputInfo to set dwTime to 7000 (3000ms ago)
        def fake_get_last_input(lii_ptr):
            lii_ptr.dwTime = 7000
            return True

        mock_ctypes.windll.user32.GetLastInputInfo.side_effect = fake_get_last_input
        mock_ctypes.byref.side_effect = lambda x: x

        assert is_user_idle(threshold_ms=2000) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    @patch("src.utils.idle_check.ctypes")
    def test_not_idle_below_threshold(self, mock_ctypes):
        """User provided input recently."""
        mock_ctypes.windll.kernel32.GetTickCount.return_value = 10000
        mock_ctypes.sizeof.return_value = 8

        def fake_get_last_input(lii_ptr):
            lii_ptr.dwTime = 9500  # 500ms ago
            return True

        mock_ctypes.windll.user32.GetLastInputInfo.side_effect = fake_get_last_input
        mock_ctypes.byref.side_effect = lambda x: x

        assert is_user_idle(threshold_ms=2000) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    @patch("src.utils.idle_check.ctypes")
    def test_synthetic_input_ignored(self, mock_ctypes):
        """Our own synthetic input should not count as user activity."""
        mock_ctypes.windll.kernel32.GetTickCount.return_value = 10000
        mock_ctypes.sizeof.return_value = 8

        # Record synthetic input at tick 9900
        idle_module._last_synthetic_input_tick = 9900

        def fake_get_last_input(lii_ptr):
            lii_ptr.dwTime = 9950  # Matches synthetic within tolerance
            return True

        mock_ctypes.windll.user32.GetLastInputInfo.side_effect = fake_get_last_input
        mock_ctypes.byref.side_effect = lambda x: x

        # Should be True because the input was synthetic
        assert is_user_idle(threshold_ms=2000) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    @patch("src.utils.idle_check.ctypes")
    def test_api_failure_returns_true(self, mock_ctypes):
        """GetLastInputInfo failure should assume idle."""
        mock_ctypes.sizeof.return_value = 8
        mock_ctypes.windll.user32.GetLastInputInfo.return_value = False
        mock_ctypes.byref.side_effect = lambda x: x

        assert is_user_idle() is True


class TestMarkSyntheticInput:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    @patch("src.utils.idle_check.ctypes")
    def test_updates_tick(self, mock_ctypes):
        mock_ctypes.windll.kernel32.GetTickCount.return_value = 12345
        mark_synthetic_input()
        assert idle_module._last_synthetic_input_tick == 12345

    def test_noop_on_non_windows(self):
        """mark_synthetic_input should be safe on non-Windows."""
        with patch.object(idle_module, "sys") as mock_sys:
            mock_sys.platform = "linux"
            # Should not raise
            mark_synthetic_input()
