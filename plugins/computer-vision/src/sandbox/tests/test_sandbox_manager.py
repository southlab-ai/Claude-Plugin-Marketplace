"""Tests for SandboxLifecycleManager (mock subprocess, filesystem).

Tests the sandbox lifecycle manager from src/sandbox/lifecycle/sandbox_manager.py.
All subprocess, IPC, and filesystem interactions are mocked.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.sandbox.lifecycle.sandbox_manager import SandboxLifecycleManager


@pytest.fixture
def dll_folder(tmp_path: Path) -> Path:
    """Create a temp folder acting as the DLL folder."""
    folder = tmp_path / "dlls"
    folder.mkdir()
    (folder / "shim64.dll").write_bytes(b"fake")
    (folder / "inject_and_run.ps1").write_text("# fake script")
    return folder


@pytest.fixture
def manager(dll_folder: Path) -> SandboxLifecycleManager:
    """Create a SandboxLifecycleManager with a temp DLL folder."""
    return SandboxLifecycleManager(dll_folder=dll_folder)


class TestWsbGeneration:
    """Test .wsb configuration file generation."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_wsb_generation(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Verify .wsb XML has correct structure after start()."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1000
        mock_popen.return_value = mock_proc

        result = manager.start(exe_path="C:\\test.exe", timeout=5.0)
        assert result is True

        # The .wsb file should have been generated
        wsb_path = manager._wsb_path
        assert wsb_path is not None and wsb_path.exists()

        tree = ET.parse(wsb_path)
        root = tree.getroot()
        assert root.tag == "Configuration"

        tags = {child.tag for child in root}
        assert "Networking" in tags
        assert "VGpu" in tags
        assert "ClipboardRedirection" in tags
        assert "MappedFolders" in tags
        assert "LogonCommand" in tags

        manager.stop()


class TestStartStop:
    """Test sandbox start/stop lifecycle."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_start_success(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Mock subprocess + port discovery -> returns True."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1000
        mock_popen.return_value = mock_proc

        result = manager.start(exe_path="C:\\test.exe", timeout=5.0)
        assert result is True
        mock_popen.assert_called_once()
        manager.stop()

    @patch("subprocess.Popen")
    @patch(
        "src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port",
        side_effect=TimeoutError("no port"),
    )
    def test_start_timeout(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Port file never appears in time -> returns False."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1001
        mock_popen.return_value = mock_proc

        result = manager.start(exe_path="C:\\test.exe", timeout=0.1)
        assert result is False

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_stop_terminates(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Verify process.terminate() called on stop()."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1002
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        manager.stop()
        mock_proc.terminate.assert_called_once()


class TestCleanup:
    """Test temp file cleanup."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_cleanup_removes_files(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Verify temp files deleted after stop()."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1003
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        temp_dir = manager._temp_dir
        assert temp_dir is not None and temp_dir.exists()

        manager.stop()
        # After stop, the temp directory should be cleaned up
        assert not temp_dir.exists()


class TestAuthToken:
    """Test auth token generation."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_auth_token_generated(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Verify 256-bit token (64 hex chars) written during start."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1004
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        token = manager._token
        assert isinstance(token, str)
        assert len(token) == 64
        # Verify it's valid hex
        int(token, 16)

        # Verify it was written to the comm folder
        comm_folder = manager._comm_folder
        assert comm_folder is not None
        token_file = comm_folder / "auth_token.txt"
        assert token_file.exists()
        assert token_file.read_text(encoding="utf-8") == token

        manager.stop()


class TestReadiness:
    """Test is_ready checks."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_is_ready_connected(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """After successful start, is_ready() returns True."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process still running
        mock_proc.pid = 1005
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        assert manager.is_ready() is True
        manager.stop()

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_is_ready_disconnected(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """Process terminated -> is_ready() returns False."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1006
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)

        # Simulate process termination
        mock_proc.poll.return_value = 1  # exit code = 1
        assert manager.is_ready() is False
        manager.stop()


class TestWsbSecurityFromManager:
    """Verify security settings in generated .wsb files."""

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_wsb_clipboard_disabled(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """.wsb has ClipboardRedirection=Disable."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 2000
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        tree = ET.parse(manager._wsb_path)
        clip = tree.getroot().find("ClipboardRedirection")
        assert clip is not None
        assert clip.text == "Disable"
        manager.stop()

    @patch("subprocess.Popen")
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient.discover_port", return_value=9876)
    def test_wsb_vgpu_disabled(
        self,
        mock_port: MagicMock,
        mock_popen: MagicMock,
        manager: SandboxLifecycleManager,
    ) -> None:
        """.wsb has VGpu=Disable."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 2001
        mock_popen.return_value = mock_proc

        manager.start(exe_path="C:\\test.exe", timeout=5.0)
        tree = ET.parse(manager._wsb_path)
        vgpu = tree.getroot().find("VGpu")
        assert vgpu is not None
        assert vgpu.text == "Disable"
        manager.stop()
