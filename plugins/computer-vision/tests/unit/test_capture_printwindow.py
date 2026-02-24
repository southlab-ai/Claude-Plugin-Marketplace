"""Unit tests for PrintWindow-first 3-tier capture fallback in src/utils/screenshot.py."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, call

import pytest
from PIL import Image

from src.errors import CVPluginError


HWND = 12345


def _make_image(width: int = 100, height: int = 100, color: tuple = (128, 64, 32)) -> Image.Image:
    """Create a test PIL image with a given solid color."""
    return Image.new("RGB", (width, height), color)


def _make_black_image(width: int = 100, height: int = 100) -> Image.Image:
    """Create an all-black PIL image."""
    return Image.new("RGB", (width, height), (0, 0, 0))


class TestIsAllBlack:
    """Tests for _is_all_black helper."""

    def test_black_image_detected(self):
        from src.utils.screenshot import _is_all_black
        img = _make_black_image()
        assert _is_all_black(img) is True

    def test_normal_image_passes(self):
        from src.utils.screenshot import _is_all_black
        img = _make_image(color=(100, 200, 50))
        assert _is_all_black(img) is False

    def test_mostly_black_with_some_content_passes(self):
        from src.utils.screenshot import _is_all_black
        img = _make_black_image(100, 100)
        # Set one pixel to non-black
        img.putpixel((50, 50), (255, 255, 255))
        assert _is_all_black(img) is False

    def test_single_channel_black(self):
        from src.utils.screenshot import _is_all_black
        img = Image.new("L", (10, 10), 0)
        assert _is_all_black(img) is True

    def test_single_channel_nonblack(self):
        from src.utils.screenshot import _is_all_black
        img = Image.new("L", (10, 10), 128)
        assert _is_all_black(img) is False


class TestCaptureWithPrintwindow:
    """Tests for _capture_with_printwindow with flag parameter."""

    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.win32ui")
    @patch("src.utils.screenshot.ctypes")
    def test_flag_parameter_passed_to_printwindow(self, mock_ctypes, mock_win32ui, mock_win32gui):
        mock_hdc_window = 1001
        mock_win32gui.GetWindowDC.return_value = mock_hdc_window

        mock_hdc_mem = MagicMock()
        mock_win32ui.CreateDCFromHandle.return_value = mock_hdc_mem
        mock_hdc_compat = MagicMock()
        mock_hdc_mem.CreateCompatibleDC.return_value = mock_hdc_compat
        mock_hdc_compat.GetSafeHdc.return_value = 2002

        mock_bitmap = MagicMock()
        mock_win32ui.CreateBitmap.return_value = mock_bitmap
        mock_bitmap.GetInfo.return_value = {"bmWidth": 100, "bmHeight": 100}
        mock_bitmap.GetBitmapBits.return_value = b"\x00" * (100 * 100 * 4)

        mock_ctypes.windll.user32.PrintWindow.return_value = 1

        from src.utils.screenshot import _capture_with_printwindow

        # Test with flag=2 (PW_RENDERFULLCONTENT)
        _capture_with_printwindow(HWND, 100, 100, flag=2)
        mock_ctypes.windll.user32.PrintWindow.assert_called_with(HWND, 2002, 2)

        mock_ctypes.windll.user32.PrintWindow.reset_mock()

        # Test with flag=0
        _capture_with_printwindow(HWND, 100, 100, flag=0)
        mock_ctypes.windll.user32.PrintWindow.assert_called_with(HWND, 2002, 0)

    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.win32ui")
    @patch("src.utils.screenshot.ctypes")
    def test_returns_none_when_printwindow_fails(self, mock_ctypes, mock_win32ui, mock_win32gui):
        mock_win32gui.GetWindowDC.return_value = 1001
        mock_hdc_mem = MagicMock()
        mock_win32ui.CreateDCFromHandle.return_value = mock_hdc_mem
        mock_hdc_compat = MagicMock()
        mock_hdc_mem.CreateCompatibleDC.return_value = mock_hdc_compat

        mock_bitmap = MagicMock()
        mock_win32ui.CreateBitmap.return_value = mock_bitmap

        mock_ctypes.windll.user32.PrintWindow.return_value = 0

        from src.utils.screenshot import _capture_with_printwindow
        result = _capture_with_printwindow(HWND, 100, 100, flag=2)
        assert result is None

    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.win32ui")
    @patch("src.utils.screenshot.ctypes")
    def test_gdi_cleanup_on_success(self, mock_ctypes, mock_win32ui, mock_win32gui):
        mock_hdc_window = 1001
        mock_win32gui.GetWindowDC.return_value = mock_hdc_window
        mock_hdc_mem = MagicMock()
        mock_win32ui.CreateDCFromHandle.return_value = mock_hdc_mem
        mock_hdc_compat = MagicMock()
        mock_hdc_mem.CreateCompatibleDC.return_value = mock_hdc_compat
        mock_hdc_compat.GetSafeHdc.return_value = 2002

        mock_bitmap = MagicMock()
        mock_bitmap.GetHandle.return_value = 3003
        mock_win32ui.CreateBitmap.return_value = mock_bitmap
        mock_bitmap.GetInfo.return_value = {"bmWidth": 50, "bmHeight": 50}
        mock_bitmap.GetBitmapBits.return_value = b"\x00" * (50 * 50 * 4)

        mock_ctypes.windll.user32.PrintWindow.return_value = 1

        from src.utils.screenshot import _capture_with_printwindow
        _capture_with_printwindow(HWND, 50, 50, flag=2)

        # Verify GDI cleanup
        mock_win32gui.DeleteObject.assert_called_once_with(3003)
        mock_hdc_compat.DeleteDC.assert_called_once()
        mock_hdc_mem.DeleteDC.assert_called_once()
        mock_win32gui.ReleaseDC.assert_called_once_with(HWND, mock_hdc_window)


class TestCaptureWindowImpl:
    """Tests for _capture_window_impl 3-tier fallback."""

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_tier1_pw_renderfullcontent_success(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = False
        mock_win32gui.GetWindowRect.return_value = (0, 0, 800, 600)

        good_img = _make_image(800, 600)
        mock_pw.return_value = good_img

        from src.utils.screenshot import _capture_window_impl
        result = _capture_window_impl(HWND)

        assert result is good_img
        mock_pw.assert_called_once_with(HWND, 800, 600, flag=2)
        mock_mss.assert_not_called()

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_tier1_black_falls_through_to_tier2(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = False
        mock_win32gui.GetWindowRect.return_value = (0, 0, 100, 100)

        black_img = _make_black_image()
        good_img = _make_image()
        # flag=2 returns black, flag=0 returns good
        mock_pw.side_effect = [black_img, good_img]

        from src.utils.screenshot import _capture_window_impl
        result = _capture_window_impl(HWND)

        assert result is good_img
        assert mock_pw.call_count == 2
        mock_pw.assert_any_call(HWND, 100, 100, flag=2)
        mock_pw.assert_any_call(HWND, 100, 100, flag=0)
        mock_mss.assert_not_called()

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_tier2_black_falls_through_to_tier3_mss(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = False
        mock_win32gui.GetWindowRect.return_value = (10, 20, 110, 120)

        black_img = _make_black_image()
        mss_img = _make_image()
        mock_pw.return_value = black_img
        mock_mss.return_value = mss_img

        from src.utils.screenshot import _capture_window_impl
        result = _capture_window_impl(HWND)

        assert result is mss_img
        assert mock_pw.call_count == 2
        mock_mss.assert_called_once_with(10, 20, 100, 100)

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_all_tiers_fail_raises_error(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = False
        mock_win32gui.GetWindowRect.return_value = (0, 0, 100, 100)

        mock_pw.return_value = None
        mock_mss.return_value = None

        from src.utils.screenshot import _capture_window_impl
        with pytest.raises(CVPluginError) as exc_info:
            _capture_window_impl(HWND)
        assert "CAPTURE_FAILED" in str(exc_info.value.code)

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_minimized_window_shown_then_reminimized(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = True
        mock_win32gui.GetWindowRect.return_value = (0, 0, 800, 600)

        good_img = _make_image(800, 600)
        mock_pw.return_value = good_img

        from src.utils.screenshot import _capture_window_impl
        result = _capture_window_impl(HWND)

        assert result is good_img
        # Check ShowWindow called with SW_SHOWNOACTIVATE (4) before capture
        # and SW_MINIMIZE (6) after capture (in finally)
        show_calls = mock_win32gui.ShowWindow.call_args_list
        assert len(show_calls) == 2
        assert show_calls[0] == call(HWND, 4)   # SW_SHOWNOACTIVATE
        assert show_calls[1] == call(HWND, 6)   # SW_MINIMIZE

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_minimized_reminimized_even_on_error(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = True
        mock_win32gui.GetWindowRect.return_value = (0, 0, 100, 100)

        mock_pw.return_value = None
        mock_mss.return_value = None

        from src.utils.screenshot import _capture_window_impl
        with pytest.raises(CVPluginError):
            _capture_window_impl(HWND)

        # Even on error, SW_MINIMIZE should be called in finally
        show_calls = mock_win32gui.ShowWindow.call_args_list
        assert call(HWND, 6) in show_calls

    @patch("src.utils.screenshot._capture_region_mss")
    @patch("src.utils.screenshot._capture_with_printwindow")
    @patch("src.utils.screenshot.win32gui")
    @patch("src.utils.screenshot.ctypes")
    def test_zero_size_window_raises(self, mock_ctypes, mock_win32gui, mock_pw, mock_mss):
        mock_ctypes.windll.user32.IsIconic.return_value = False
        mock_win32gui.GetWindowRect.return_value = (100, 100, 100, 100)  # zero size

        from src.utils.screenshot import _capture_window_impl
        with pytest.raises(CVPluginError) as exc_info:
            _capture_window_impl(HWND)
        assert "zero size" in str(exc_info.value.message)


class TestCaptureWindowRawUsesImpl:
    """Test that capture_window_raw delegates to _capture_window_impl."""

    @patch("src.utils.screenshot._capture_window_impl")
    @patch("src.utils.screenshot.is_window_valid", return_value=True)
    def test_delegates_to_impl(self, mock_valid, mock_impl):
        expected_img = _make_image()
        mock_impl.return_value = expected_img

        from src.utils.screenshot import capture_window_raw
        result = capture_window_raw(HWND)
        assert result is expected_img
        mock_impl.assert_called_once_with(HWND)

    @patch("src.utils.screenshot._capture_window_impl")
    @patch("src.utils.screenshot.is_window_valid", return_value=True)
    def test_returns_none_on_impl_exception(self, mock_valid, mock_impl):
        mock_impl.side_effect = Exception("capture failed")

        from src.utils.screenshot import capture_window_raw
        result = capture_window_raw(HWND)
        assert result is None

    @patch("src.utils.screenshot.is_window_valid", return_value=False)
    def test_returns_none_for_invalid_window(self, mock_valid):
        from src.utils.screenshot import capture_window_raw
        result = capture_window_raw(HWND)
        assert result is None
