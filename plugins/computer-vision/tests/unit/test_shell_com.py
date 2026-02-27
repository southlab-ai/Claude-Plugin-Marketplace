"""Unit tests for ShellCOMAdapter."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.adapters.shell_com import ShellCOMAdapter


@pytest.fixture
def adapter():
    """Create a fresh ShellCOMAdapter for each test."""
    return ShellCOMAdapter()


class TestShellCOMProbe:
    """Tests for probe behavior."""

    def test_probe_success(self, adapter):
        """probe returns True for explorer.exe with CabinetWClass."""
        with patch("src.adapters.shell_com.ctypes") as mock_ctypes:
            # Mock GetClassNameW to return CabinetWClass
            mock_buf = MagicMock()
            mock_buf.value = "CabinetWClass"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            # Mock GetWindowThreadProcessId
            mock_pid = MagicMock()
            mock_pid.value = 1234
            mock_ctypes.c_ulong.return_value = mock_pid

            with patch("src.utils.security.get_process_name_by_pid", return_value="explorer"):
                result = adapter.probe(12345)
                assert result is True

    def test_probe_failure_wrong_class(self, adapter):
        """probe returns False when window class is not CabinetWClass."""
        with patch("src.adapters.shell_com.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "NotExplorer"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            result = adapter.probe(12345)
            assert result is False

    def test_probe_failure_wrong_process(self, adapter):
        """probe returns False when process is not explorer.exe."""
        with patch("src.adapters.shell_com.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "CabinetWClass"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            mock_pid = MagicMock()
            mock_pid.value = 1234
            mock_ctypes.c_ulong.return_value = mock_pid

            with patch("src.utils.security.get_process_name_by_pid", return_value="notepad"):
                result = adapter.probe(12345)
                assert result is False


class TestShellCOMSupportsAction:
    """Tests for supports_action."""

    def test_supports_invoke(self, adapter):
        assert adapter.supports_action("invoke") is True

    def test_supports_get_value(self, adapter):
        assert adapter.supports_action("get_value") is True

    def test_does_not_support_set_value(self, adapter):
        assert adapter.supports_action("set_value") is False


class TestShellCOMSensitivePath:
    """Tests for sensitive path filtering."""

    def test_ssh_directory_blocked(self):
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\.ssh") is True
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\.ssh\\id_rsa") is True

    def test_gnupg_directory_blocked(self):
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\.gnupg") is True
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\.gnupg\\secring.gpg") is True

    def test_vault_directory_blocked(self):
        assert ShellCOMAdapter._is_sensitive_path("C:\\AppData\\Vault\\secrets") is True

    def test_normal_path_allowed(self):
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\Documents") is False

    def test_desktop_path_allowed(self):
        assert ShellCOMAdapter._is_sensitive_path("C:\\Users\\user\\Desktop") is False

    def test_downloads_path_allowed(self):
        assert ShellCOMAdapter._is_sensitive_path("D:\\Downloads\\file.txt") is False


class TestShellCOMExecute:
    """Tests for execute method."""

    def test_execute_get_value(self, adapter):
        """get_value returns current path of Explorer window."""
        mock_window = MagicMock()
        mock_window.HWND = 12345
        mock_window.LocationURL = "file:///C:/Users/test/Documents"
        mock_window.LocationName = "Documents"

        mock_windows = MagicMock()
        mock_windows.Count = 1
        mock_windows.Item.return_value = mock_window

        mock_shell = MagicMock()
        mock_shell.Windows.return_value = mock_windows

        mock_client = MagicMock()
        mock_client.Dispatch.return_value = mock_shell
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client

        with patch.dict("sys.modules", {"win32com": mock_win32com, "win32com.client": mock_client}):
            result = adapter.execute(12345, "", "get_value", None)
            assert result.success is True
            assert "path" in result.element

    def test_execute_navigate_normal_path(self, adapter):
        """invoke navigates to a normal path."""
        mock_window = MagicMock()
        mock_window.HWND = 12345

        mock_windows = MagicMock()
        mock_windows.Count = 1
        mock_windows.Item.return_value = mock_window

        mock_shell = MagicMock()
        mock_shell.Windows.return_value = mock_windows

        mock_client = MagicMock()
        mock_client.Dispatch.return_value = mock_shell
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client

        with patch.dict("sys.modules", {"win32com": mock_win32com, "win32com.client": mock_client}):
            result = adapter.execute(12345, "C:\\Users\\test\\Documents", "invoke", None)
            assert result.success is True
            mock_window.Navigate.assert_called_once()

    def test_execute_navigate_sensitive_path_blocked(self, adapter):
        """invoke blocks navigation to sensitive paths."""
        result = adapter.execute(12345, "C:\\Users\\test\\.ssh", "invoke", None)
        assert result.success is False

    def test_execute_unsupported_action(self, adapter):
        """Unsupported actions return failure."""
        result = adapter.execute(12345, "C:\\", "set_value", "test")
        assert result.success is False
