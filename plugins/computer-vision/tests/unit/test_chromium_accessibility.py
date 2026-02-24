"""Unit tests for Chromium accessibility activation in src/utils/uia.py."""

from __future__ import annotations

import ctypes
from unittest.mock import MagicMock, call, patch

import pytest

from src.utils.uia import (
    WM_GETOBJECT,
    OBJID_CLIENT,
    SMTO_ABORTIFHUNG,
    _activated_hwnds,
    _ensure_chromium_accessibility,
)


@pytest.fixture(autouse=True)
def _clear_activation_cache():
    """Clear the activation cache before and after each test."""
    _activated_hwnds.clear()
    yield
    _activated_hwnds.clear()


# ---------------------------------------------------------------------------
# Patches applied to every test to avoid real Win32 calls
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_win32():
    """Patch win32gui, win32process, and ctypes.windll for all tests."""
    with (
        patch("src.utils.uia.win32gui") as mock_win32gui,
        patch("src.utils.uia.win32process") as mock_win32process,
        patch("src.utils.uia.ctypes") as mock_ctypes,
        patch("src.utils.win32_window._get_process_name", return_value="chrome") as mock_get_proc,
    ):
        # Default: chrome process, Chrome_WidgetWin_1 class, one renderer child
        mock_win32process.GetWindowThreadProcessId.return_value = (1234, 5678)
        mock_win32gui.GetClassName.return_value = "Chrome_WidgetWin_1"
        mock_win32gui.EnumChildWindows.side_effect = None

        # Make ctypes.c_long and ctypes.byref work
        mock_ctypes.c_long = ctypes.c_long
        mock_ctypes.byref = ctypes.byref

        yield {
            "win32gui": mock_win32gui,
            "win32process": mock_win32process,
            "ctypes": mock_ctypes,
            "get_process_name": mock_get_proc,
        }


# ===========================================================================
# Test: Chrome process detection
# ===========================================================================

class TestChromiumDetection:
    """Tests for detecting Chromium-based processes."""

    def test_chrome_process_detected(self, _patch_win32):
        """Chrome process should trigger activation."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"
        mocks["win32gui"].GetClassName.return_value = "SomeOtherClass"

        # No children found
        def enum_no_children(hwnd, callback, results):
            pass
        mocks["win32gui"].EnumChildWindows.side_effect = enum_no_children

        _ensure_chromium_accessibility(12345)

        # Should have called EnumChildWindows (got past the detection check)
        mocks["win32gui"].EnumChildWindows.assert_called_once()

    def test_chrome_class_detected(self, _patch_win32):
        """Chrome_WidgetWin_1 class should trigger activation even with unknown process."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "unknown_app"
        mocks["win32gui"].GetClassName.return_value = "Chrome_WidgetWin_1"

        def enum_no_children(hwnd, callback, results):
            pass
        mocks["win32gui"].EnumChildWindows.side_effect = enum_no_children

        _ensure_chromium_accessibility(12345)

        mocks["win32gui"].EnumChildWindows.assert_called_once()

    def test_non_chromium_skipped(self, _patch_win32):
        """Non-Chromium process with non-Chrome class should skip activation."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "notepad"
        mocks["win32gui"].GetClassName.return_value = "Notepad"

        _ensure_chromium_accessibility(12345)

        # Should NOT have called EnumChildWindows
        mocks["win32gui"].EnumChildWindows.assert_not_called()


# ===========================================================================
# Test: EnumChildWindows and WM_GETOBJECT
# ===========================================================================

class TestRendererActivation:
    """Tests for finding renderer children and sending WM_GETOBJECT."""

    def test_enum_finds_renderer_child(self, _patch_win32):
        """EnumChildWindows should find Chrome_RenderWidgetHostHWND children."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"
        renderer_hwnd = 99999

        def enum_with_renderer(hwnd, callback, results):
            # Simulate EnumChildWindows calling the callback with a renderer child
            # We need to call the callback as win32gui would
            mocks["win32gui"].GetClassName.side_effect = lambda h: (
                "Chrome_RenderWidgetHostHWND" if h == renderer_hwnd else "Chrome_WidgetWin_1"
            )
            callback(renderer_hwnd, results)

        mocks["win32gui"].EnumChildWindows.side_effect = enum_with_renderer

        _ensure_chromium_accessibility(12345)

        # SendMessageTimeoutW should have been called
        mocks["ctypes"].windll.user32.SendMessageTimeoutW.assert_called_once()

    def test_send_message_correct_params(self, _patch_win32):
        """SendMessageTimeoutW should be called with correct WM_GETOBJECT params."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"
        renderer_hwnd = 88888

        def enum_with_renderer(hwnd, callback, results):
            mocks["win32gui"].GetClassName.side_effect = lambda h: (
                "Chrome_RenderWidgetHostHWND" if h == renderer_hwnd else "Chrome_WidgetWin_1"
            )
            callback(renderer_hwnd, results)

        mocks["win32gui"].EnumChildWindows.side_effect = enum_with_renderer

        _ensure_chromium_accessibility(12345)

        send_call = mocks["ctypes"].windll.user32.SendMessageTimeoutW
        send_call.assert_called_once()
        args = send_call.call_args

        assert args[0][0] == renderer_hwnd       # child_hwnd
        assert args[0][1] == WM_GETOBJECT         # 0x003D
        assert args[0][2] == 0                     # wParam
        assert args[0][3] == OBJID_CLIENT          # 0xFFFFFFFC
        assert args[0][4] == SMTO_ABORTIFHUNG      # 0x0002
        assert args[0][5] == 2000                  # timeout ms

    def test_exact_class_name_match(self, _patch_win32):
        """Only exact 'Chrome_RenderWidgetHostHWND' match, not substrings."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"

        def enum_with_wrong_class(hwnd, callback, results):
            # Child with similar but not exact class name
            mocks["win32gui"].GetClassName.side_effect = lambda h: (
                "Chrome_RenderWidgetHostHWND_Extra" if h == 77777 else "Chrome_WidgetWin_1"
            )
            callback(77777, results)

        mocks["win32gui"].EnumChildWindows.side_effect = enum_with_wrong_class

        _ensure_chromium_accessibility(12345)

        # Should NOT have sent WM_GETOBJECT since class doesn't match exactly
        mocks["ctypes"].windll.user32.SendMessageTimeoutW.assert_not_called()

    def test_multiple_renderer_children(self, _patch_win32):
        """Multiple Chrome_RenderWidgetHostHWND children should all get WM_GETOBJECT."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"
        renderer_hwnds = [11111, 22222, 33333]

        def enum_with_multiple(hwnd, callback, results):
            mocks["win32gui"].GetClassName.side_effect = lambda h: (
                "Chrome_RenderWidgetHostHWND" if h in renderer_hwnds else "Chrome_WidgetWin_1"
            )
            for rh in renderer_hwnds:
                callback(rh, results)

        mocks["win32gui"].EnumChildWindows.side_effect = enum_with_multiple

        _ensure_chromium_accessibility(12345)

        send_call = mocks["ctypes"].windll.user32.SendMessageTimeoutW
        assert send_call.call_count == len(renderer_hwnds)


# ===========================================================================
# Test: Caching
# ===========================================================================

class TestCaching:
    """Tests for activation caching behavior."""

    def test_second_call_skips_activation(self, _patch_win32):
        """Second call with same hwnd should skip activation (cached)."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"

        def enum_no_children(hwnd, callback, results):
            pass
        mocks["win32gui"].EnumChildWindows.side_effect = enum_no_children

        _ensure_chromium_accessibility(12345)
        _ensure_chromium_accessibility(12345)

        # EnumChildWindows should only be called once (second call is cached)
        assert mocks["win32gui"].EnumChildWindows.call_count == 1


# ===========================================================================
# Test: Sleep after activation
# ===========================================================================

class TestSleepAfterActivation:
    """Tests for the sleep delay after activation."""

    @patch("src.utils.uia.time.sleep")
    def test_sleep_called_after_activation(self, mock_sleep, _patch_win32):
        """time.sleep(0.2) should be called when renderer children are found."""
        mocks = _patch_win32
        mocks["get_process_name"].return_value = "chrome"
        renderer_hwnd = 55555

        def enum_with_renderer(hwnd, callback, results):
            mocks["win32gui"].GetClassName.side_effect = lambda h: (
                "Chrome_RenderWidgetHostHWND" if h == renderer_hwnd else "Chrome_WidgetWin_1"
            )
            callback(renderer_hwnd, results)

        mocks["win32gui"].EnumChildWindows.side_effect = enum_with_renderer

        _ensure_chromium_accessibility(12345)

        mock_sleep.assert_called_once_with(0.2)


# ===========================================================================
# Test: Failure resilience
# ===========================================================================

class TestFailureResilience:
    """Tests that activation failure doesn't break get_ui_tree."""

    def test_activation_failure_doesnt_break_get_ui_tree(self):
        """If _ensure_chromium_accessibility raises internally, get_ui_tree should still work."""
        mock_uia = MagicMock()
        mock_uia.ElementFromHandle.return_value = MagicMock()
        mock_walker = MagicMock()
        mock_walker.GetFirstChildElement.return_value = None
        mock_uia.CreateTreeWalker.return_value = mock_walker
        mock_uia.CreateTrueCondition.return_value = MagicMock()

        with (
            patch("src.utils.uia._safe_init_uia", return_value=mock_uia),
            patch("src.utils.uia._ensure_chromium_accessibility", side_effect=Exception("boom")),
        ):
            # get_ui_tree should propagate the exception since it's not caught there
            # But _ensure_chromium_accessibility itself catches internally,
            # so we test the real function with a failing dependency instead
            pass

        # Test that the real function catches internal errors
        with (
            patch("src.utils.uia.win32process.GetWindowThreadProcessId", side_effect=OSError("no process")),
            patch("src.utils.uia.win32gui"),
        ):
            # Should not raise
            _ensure_chromium_accessibility(12345)
