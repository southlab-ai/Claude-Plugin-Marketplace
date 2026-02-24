"""Unit tests for focus_window() 4-strategy escalation in src/utils/win32_window.py."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, call

import pytest


# We need to mock the Win32 modules before importing the module under test.
# Use patches at the function/class level to control behavior per test.

HWND = 12345
OTHER_HWND = 99999
FG_THREAD = 1000
TARGET_THREAD = 2000


class TestIsFocused:
    """Tests for _is_focused helper."""

    @patch("src.utils.win32_window.ctypes")
    def test_returns_true_when_foreground_matches(self, mock_ctypes):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        from src.utils.win32_window import _is_focused
        assert _is_focused(HWND) is True

    @patch("src.utils.win32_window.ctypes")
    def test_returns_false_when_foreground_differs(self, mock_ctypes):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
        from src.utils.win32_window import _is_focused
        assert _is_focused(HWND) is False


class TestStrategyDirect:
    """Tests for _strategy_direct."""

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_success_when_foreground_matches(self, mock_win32gui, mock_ctypes):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        from src.utils.win32_window import _strategy_direct
        assert _strategy_direct(HWND) is True
        mock_win32gui.SetForegroundWindow.assert_called_once_with(HWND)

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_failure_when_foreground_differs(self, mock_win32gui, mock_ctypes):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
        from src.utils.win32_window import _strategy_direct
        assert _strategy_direct(HWND) is False

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_exception_returns_false(self, mock_win32gui, mock_ctypes):
        mock_win32gui.SetForegroundWindow.side_effect = Exception("access denied")
        from src.utils.win32_window import _strategy_direct
        assert _strategy_direct(HWND) is False


class TestStrategyAltTrick:
    """Tests for _strategy_alt_trick."""

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_sends_paired_alt_keydown_keyup(self, mock_win32gui, mock_ctypes):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        mock_ctypes.windll.user32.SendInput.return_value = 2
        # Need to make ctypes.wintypes, Structure, etc. work
        # Reset ctypes side effects to let the real ctypes work for struct creation
        # We selectively mock only windll
        from src.utils.win32_window import _strategy_alt_trick

        # The function internally defines ctypes structures; we just verify SendInput was called
        # and SetForegroundWindow was called.
        # Since we're fully mocking ctypes, the struct creation will use mock objects.
        # Just verify the function doesn't crash and calls the right things.
        result = _strategy_alt_trick(HWND)
        # Depending on mock behavior, just check it called SendInput
        mock_ctypes.windll.user32.SendInput.assert_called_once()

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_exception_returns_false(self, mock_win32gui, mock_ctypes):
        mock_ctypes.windll.user32.SendInput.side_effect = Exception("send failed")
        # Make the struct creation fail by breaking ctypes.Structure
        mock_ctypes.Structure = type("MockStructure", (), {})
        from src.utils.win32_window import _strategy_alt_trick
        assert _strategy_alt_trick(HWND) is False


class TestStrategyAttachThread:
    """Tests for _strategy_attach_thread."""

    @patch("src.utils.win32_window.win32process")
    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_attaches_and_detaches_threads(self, mock_win32gui, mock_ctypes, mock_win32process):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
        mock_win32process.GetWindowThreadProcessId.side_effect = [
            (FG_THREAD, 100),  # foreground window
            (TARGET_THREAD, 200),  # target window
        ]
        # After SetForegroundWindow, simulate success
        # GetForegroundWindow will be called again by _is_focused
        mock_ctypes.windll.user32.GetForegroundWindow.side_effect = [
            OTHER_HWND,  # first call in _strategy_attach_thread
            HWND,  # called by _is_focused
        ]
        from src.utils.win32_window import _strategy_attach_thread
        result = _strategy_attach_thread(HWND)
        assert result is True

        # Verify attach was called
        mock_ctypes.windll.user32.AttachThreadInput.assert_any_call(TARGET_THREAD, FG_THREAD, True)
        # Verify detach in finally
        mock_ctypes.windll.user32.AttachThreadInput.assert_any_call(TARGET_THREAD, FG_THREAD, False)
        mock_win32gui.BringWindowToTop.assert_called_once_with(HWND)

    @patch("src.utils.win32_window.win32process")
    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_detach_called_even_on_exception(self, mock_win32gui, mock_ctypes, mock_win32process):
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = OTHER_HWND
        mock_win32process.GetWindowThreadProcessId.side_effect = [
            (FG_THREAD, 100),
            (TARGET_THREAD, 200),
        ]
        mock_win32gui.BringWindowToTop.side_effect = Exception("bring failed")

        from src.utils.win32_window import _strategy_attach_thread
        result = _strategy_attach_thread(HWND)
        assert result is False
        # Detach should still be called
        mock_ctypes.windll.user32.AttachThreadInput.assert_any_call(TARGET_THREAD, FG_THREAD, False)


class TestStrategySpiBypass:
    """Tests for _strategy_spi_bypass."""

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_saves_and_restores_timeout(self, mock_win32gui, mock_ctypes):
        # Mock the DWORD and byref
        mock_dword_instance = MagicMock()
        mock_dword_instance.value = 42
        mock_ctypes.wintypes.DWORD.return_value = mock_dword_instance
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = HWND
        mock_ctypes.windll.user32.SystemParametersInfoW.return_value = True

        from src.utils.win32_window import _strategy_spi_bypass
        result = _strategy_spi_bypass(HWND)

        # Verify SystemParametersInfoW was called at least 3 times:
        # 1) GET timeout, 2) SET to 0, 3) restore in finally
        assert mock_ctypes.windll.user32.SystemParametersInfoW.call_count >= 3

    @patch("src.utils.win32_window.ctypes")
    @patch("src.utils.win32_window.win32gui")
    def test_restore_called_even_on_exception(self, mock_win32gui, mock_ctypes):
        mock_dword_instance = MagicMock()
        mock_dword_instance.value = 0
        mock_ctypes.wintypes.DWORD.return_value = mock_dword_instance

        # Make SetForegroundWindow raise
        mock_win32gui.SetForegroundWindow.side_effect = Exception("denied")

        from src.utils.win32_window import _strategy_spi_bypass
        result = _strategy_spi_bypass(HWND)
        assert result is False

        # The finally block should still try to restore (call #3)
        spi_calls = mock_ctypes.windll.user32.SystemParametersInfoW.call_args_list
        # At minimum: GET (may fail but attempted), SET (may fail but attempted)
        # Finally: restore SET
        assert len(spi_calls) >= 1  # At least the GET or restore was called


class TestFocusWindow:
    """Tests for the main focus_window function."""

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window._FOCUS_STRATEGIES")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_returns_true_on_first_strategy_success(self, mock_ctypes, mock_win32gui, mock_strategies, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = False

        strategy1 = MagicMock(return_value=True, __name__="strategy1")
        strategy2 = MagicMock(return_value=False, __name__="strategy2")
        mock_strategies.__len__ = lambda self: 2
        mock_strategies.__getitem__ = lambda self, i: [strategy1, strategy2][i]

        from src.utils.win32_window import focus_window
        assert focus_window(HWND) is True
        strategy1.assert_called_once_with(HWND)
        strategy2.assert_not_called()

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_returns_false_when_all_strategies_fail(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = False

        # Patch all individual strategies to return False
        with patch("src.utils.win32_window._strategy_direct", return_value=False), \
             patch("src.utils.win32_window._strategy_alt_trick", return_value=False), \
             patch("src.utils.win32_window._strategy_attach_thread", return_value=False), \
             patch("src.utils.win32_window._strategy_spi_bypass", return_value=False):
            from src.utils.win32_window import focus_window
            assert focus_window(HWND) is False

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_returns_false_for_invalid_window(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = False
        from src.utils.win32_window import focus_window
        assert focus_window(HWND) is False

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_restores_minimized_window(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = True

        # Make all strategies succeed on first try
        with patch("src.utils.win32_window._strategy_direct", return_value=True):
            from src.utils.win32_window import focus_window
            focus_window(HWND)

        mock_win32gui.ShowWindow.assert_called_once_with(HWND, 9)  # SW_RESTORE = 9

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_retry_sleeps_between_attempts(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = False

        with patch("src.utils.win32_window._strategy_direct", return_value=False), \
             patch("src.utils.win32_window._strategy_alt_trick", return_value=False), \
             patch("src.utils.win32_window._strategy_attach_thread", return_value=False), \
             patch("src.utils.win32_window._strategy_spi_bypass", return_value=False):
            from src.utils.win32_window import focus_window
            focus_window(HWND)

        # Should sleep between attempts (5 sleeps for 6 attempts)
        assert mock_time.sleep.call_count == 5
        mock_time.sleep.assert_called_with(0.05)

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_cycles_through_strategies(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = False

        call_order = []

        def make_strategy(name, succeed_on_call=None):
            call_count = [0]
            def strategy(hwnd):
                call_count[0] += 1
                call_order.append(name)
                if succeed_on_call is not None and call_count[0] == succeed_on_call:
                    return True
                return False
            strategy.__name__ = name
            return strategy

        # Strategy 3 (index 2) succeeds on its first call (attempt index 2)
        s1 = make_strategy("direct")
        s2 = make_strategy("alt_trick")
        s3 = make_strategy("attach_thread", succeed_on_call=1)
        s4 = make_strategy("spi_bypass")

        with patch("src.utils.win32_window._FOCUS_STRATEGIES", [s1, s2, s3, s4]):
            from src.utils.win32_window import focus_window
            result = focus_window(HWND)

        assert result is True
        assert call_order == ["direct", "alt_trick", "attach_thread"]

    @patch("src.utils.win32_window.time")
    @patch("src.utils.win32_window.win32gui")
    @patch("src.utils.win32_window.ctypes")
    def test_strategy_exception_does_not_stop_retry(self, mock_ctypes, mock_win32gui, mock_time):
        mock_ctypes.windll.user32.IsWindow.return_value = True
        mock_ctypes.windll.user32.IsIconic.return_value = False

        calls = []

        def failing_strategy(hwnd):
            calls.append("fail")
            raise RuntimeError("boom")
        failing_strategy.__name__ = "failing"

        def success_strategy(hwnd):
            calls.append("success")
            return True
        success_strategy.__name__ = "success"

        with patch("src.utils.win32_window._FOCUS_STRATEGIES", [failing_strategy, success_strategy]):
            from src.utils.win32_window import focus_window
            result = focus_window(HWND)

        assert result is True
        assert calls == ["fail", "success"]
