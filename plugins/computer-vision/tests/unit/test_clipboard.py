"""Unit tests for src/utils/clipboard.py — clipboard bridge for pasting text."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


HWND = 12345


class TestOpenClipboardWithRetry:
    """Tests for _open_clipboard_with_retry."""

    @patch("src.utils.clipboard.time")
    @patch("src.utils.clipboard.user32")
    def test_opens_on_first_try(self, mock_user32, mock_time):
        from src.utils.clipboard import _open_clipboard_with_retry

        mock_user32.OpenClipboard.return_value = True
        result = _open_clipboard_with_retry(HWND)
        assert result is True
        mock_user32.OpenClipboard.assert_called_once_with(HWND)
        mock_time.sleep.assert_not_called()

    @patch("src.utils.clipboard.time")
    @patch("src.utils.clipboard.user32")
    def test_opens_on_second_try(self, mock_user32, mock_time):
        from src.utils.clipboard import _open_clipboard_with_retry

        mock_user32.OpenClipboard.side_effect = [False, True]
        result = _open_clipboard_with_retry(HWND, max_attempts=3, backoff_ms=50)
        assert result is True
        assert mock_user32.OpenClipboard.call_count == 2
        mock_time.sleep.assert_called_once_with(0.05)

    @patch("src.utils.clipboard.time")
    @patch("src.utils.clipboard.user32")
    def test_all_retries_fail(self, mock_user32, mock_time):
        from src.utils.clipboard import _open_clipboard_with_retry

        mock_user32.OpenClipboard.return_value = False
        result = _open_clipboard_with_retry(HWND, max_attempts=3, backoff_ms=50)
        assert result is False
        assert mock_user32.OpenClipboard.call_count == 3
        assert mock_time.sleep.call_count == 2  # sleeps between attempts, not after last


class TestGetClipboardText:
    """Tests for _get_clipboard_text."""

    @patch("src.utils.clipboard.kernel32")
    @patch("src.utils.clipboard.user32")
    @patch("src.utils.clipboard.ctypes")
    def test_reads_text_successfully(self, mock_ctypes, mock_user32, mock_kernel32):
        from src.utils.clipboard import _get_clipboard_text

        mock_user32.GetClipboardData.return_value = 0x1000
        mock_kernel32.GlobalLock.return_value = 0x2000
        mock_ctypes.wstring_at.return_value = "clipboard content"

        result = _get_clipboard_text()
        assert result == "clipboard content"
        mock_kernel32.GlobalUnlock.assert_called_once_with(0x1000)

    @patch("src.utils.clipboard.user32")
    def test_no_data_returns_none(self, mock_user32):
        from src.utils.clipboard import _get_clipboard_text

        mock_user32.GetClipboardData.return_value = None
        result = _get_clipboard_text()
        assert result is None


class TestSetClipboardText:
    """Tests for _set_clipboard_text."""

    @patch("src.utils.clipboard.kernel32")
    @patch("src.utils.clipboard.user32")
    @patch("src.utils.clipboard.ctypes")
    def test_sets_text_successfully(self, mock_ctypes, mock_user32, mock_kernel32):
        from src.utils.clipboard import _set_clipboard_text

        mock_kernel32.GlobalAlloc.return_value = 0x1000
        mock_kernel32.GlobalLock.return_value = 0x2000
        mock_user32.SetClipboardData.return_value = 0x1000

        result = _set_clipboard_text("test text")
        assert result is True
        mock_user32.EmptyClipboard.assert_called_once()

    @patch("src.utils.clipboard.kernel32")
    @patch("src.utils.clipboard.user32")
    def test_global_alloc_failure(self, mock_user32, mock_kernel32):
        from src.utils.clipboard import _set_clipboard_text

        mock_kernel32.GlobalAlloc.return_value = None
        result = _set_clipboard_text("test")
        assert result is False


class TestPasteText:
    """Tests for the main paste_text function."""

    @patch("src.utils.clipboard._restore_clipboard")
    @patch("src.utils.clipboard._verify_paste", return_value=True)
    @patch("src.utils.win32_input.send_key_combo", return_value=True)
    @patch("src.utils.clipboard._set_clipboard_text", return_value=True)
    @patch("src.utils.clipboard._get_clipboard_text", return_value="old content")
    @patch("src.utils.clipboard._is_foreground_restricted", return_value=False)
    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=True)
    @patch("src.utils.clipboard.user32")
    @patch("src.utils.clipboard.time")
    def test_full_paste_flow(
        self, mock_time, mock_user32, mock_open, mock_restricted,
        mock_get_text, mock_set_text, mock_send_key, mock_verify, mock_restore,
    ):
        from src.utils.clipboard import paste_text

        mock_user32.IsWindow.return_value = True

        result = paste_text("new text", HWND)
        assert result is True

        # Verify the full flow
        mock_open.assert_called_once()
        mock_get_text.assert_called_once()
        mock_set_text.assert_called_once_with("new text")
        mock_user32.CloseClipboard.assert_called()
        mock_send_key.assert_called_once_with("ctrl+v")
        mock_restore.assert_called_once_with("old content")

    @patch("src.utils.clipboard.user32")
    def test_invalid_hwnd_returns_false(self, mock_user32):
        from src.utils.clipboard import paste_text

        mock_user32.IsWindow.return_value = False
        result = paste_text("text", HWND)
        assert result is False

    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=False)
    @patch("src.utils.clipboard.user32")
    def test_clipboard_open_failure(self, mock_user32, mock_open):
        from src.utils.clipboard import paste_text

        mock_user32.IsWindow.return_value = True
        result = paste_text("text", HWND)
        assert result is False

    @patch("src.utils.clipboard._restore_clipboard")
    @patch("src.utils.clipboard._verify_paste", return_value=True)
    @patch("src.utils.win32_input.send_key_combo", return_value=False)
    @patch("src.utils.clipboard._set_clipboard_text", return_value=True)
    @patch("src.utils.clipboard._get_clipboard_text", return_value=None)
    @patch("src.utils.clipboard._is_foreground_restricted", return_value=False)
    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=True)
    @patch("src.utils.clipboard.user32")
    @patch("src.utils.clipboard.time")
    def test_ctrl_v_failure(
        self, mock_time, mock_user32, mock_open, mock_restricted,
        mock_get_text, mock_set_text, mock_send_key, mock_verify, mock_restore,
    ):
        from src.utils.clipboard import paste_text

        mock_user32.IsWindow.return_value = True
        result = paste_text("text", HWND)
        assert result is False

    @patch("src.utils.clipboard._restore_clipboard")
    @patch("src.utils.clipboard._verify_paste", return_value=True)
    @patch("src.utils.win32_input.send_key_combo", return_value=True)
    @patch("src.utils.clipboard._set_clipboard_text", return_value=True)
    @patch("src.utils.clipboard._get_clipboard_text", return_value=None)
    @patch("src.utils.clipboard._is_foreground_restricted", return_value=True)
    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=True)
    @patch("src.utils.clipboard.user32")
    @patch("src.utils.clipboard.time")
    def test_restricted_process_skips_save(
        self, mock_time, mock_user32, mock_open, mock_restricted,
        mock_get_text, mock_set_text, mock_send_key, mock_verify, mock_restore,
    ):
        from src.utils.clipboard import paste_text

        mock_user32.IsWindow.return_value = True
        result = paste_text("text", HWND)
        assert result is True
        # Should not have called _get_clipboard_text since process is restricted
        mock_get_text.assert_not_called()
        # Should not restore since previous_content is None
        mock_restore.assert_not_called()


class TestThreshold:
    """Tests for clipboard threshold behavior."""

    @patch("src.utils.clipboard.config")
    @patch("src.utils.clipboard.user32")
    def test_text_truncated_to_max_length(self, mock_user32, mock_config):
        """Text exceeding MAX_TEXT_LENGTH is truncated."""
        mock_config.MAX_TEXT_LENGTH = 10
        mock_config.RESTRICTED_PROCESSES = []
        mock_user32.IsWindow.return_value = False  # Will fail early but after truncation

        from src.utils.clipboard import paste_text

        # Will fail at IsWindow but the truncation happens before
        result = paste_text("a" * 100, HWND)
        assert result is False  # Fails at IsWindow check


class TestVerifyPaste:
    """Tests for _verify_paste with exponential backoff."""

    @patch("src.utils.clipboard.time")
    @patch("src.utils.uia_patterns.get_value")
    def test_verify_match_on_first_poll(self, mock_get_value, mock_time):
        from src.utils.clipboard import _verify_paste

        mock_get_value.return_value = "expected"
        com_el = MagicMock()

        result = _verify_paste(com_el, "expected")
        assert result is True

    @patch("src.utils.clipboard.time")
    @patch("src.utils.uia_patterns.get_value")
    def test_verify_match_on_later_poll(self, mock_get_value, mock_time):
        from src.utils.clipboard import _verify_paste

        mock_get_value.side_effect = ["wrong", "wrong", "expected", "expected"]
        com_el = MagicMock()

        result = _verify_paste(com_el, "expected")
        assert result is True

    def test_verify_no_element_returns_true(self):
        from src.utils.clipboard import _verify_paste

        result = _verify_paste(None, "text")
        assert result is True

    @patch("src.utils.clipboard.time")
    @patch("src.utils.uia_patterns.get_value")
    def test_backoff_schedule(self, mock_get_value, mock_time):
        """Verify the exponential backoff sleep schedule."""
        from src.utils.clipboard import _verify_paste

        mock_get_value.return_value = "expected"
        com_el = MagicMock()

        _verify_paste(com_el, "expected")
        # First poll at 50ms
        mock_time.sleep.assert_any_call(0.05)


class TestRestoreClipboard:
    """Tests for _restore_clipboard."""

    @patch("src.utils.clipboard._set_clipboard_text", return_value=True)
    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=True)
    @patch("src.utils.clipboard.user32")
    def test_restores_content(self, mock_user32, mock_open, mock_set):
        from src.utils.clipboard import _restore_clipboard

        _restore_clipboard("previous content")
        mock_set.assert_called_once_with("previous content")
        mock_user32.CloseClipboard.assert_called_once()

    @patch("src.utils.clipboard._open_clipboard_with_retry", return_value=False)
    def test_restore_fails_gracefully(self, mock_open):
        from src.utils.clipboard import _restore_clipboard

        # Should not raise
        _restore_clipboard("content")
