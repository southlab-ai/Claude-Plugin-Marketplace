"""Sandbox lifecycle management — .wsb generation, launch, health, cleanup."""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from string import Template
from typing import Any

from src.sandbox.ipc.shim_ipc_client import ShimIPCClient

logger = logging.getLogger(__name__)

# .wsb XML template
_WSB_TEMPLATE = Template("""\
<Configuration>
  <Networking>Enable</Networking>
  <VGpu>Disable</VGpu>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>${dll_folder}</HostFolder>
      <SandboxFolder>C:\\ShimDLL</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>${comm_folder}</HostFolder>
      <SandboxFolder>C:\\ShimComm</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>${logon_command}</Command>
  </LogonCommand>
</Configuration>
""")

# Default logon command that launches the injector inside the sandbox
_DEFAULT_LOGON_CMD = (
    'powershell -ExecutionPolicy Bypass -File "C:\\ShimDLL\\inject_and_run.ps1"'
    ' -ExePath "${exe_path}"'
    ' -CommFolder "C:\\ShimComm"'
)

_BOOT_POLL_INTERVAL = 0.5  # seconds
_TOKEN_BYTES = 32  # 256-bit token


class SandboxLifecycleManager:
    """Manages the full lifecycle of a Windows Sandbox instance.

    Responsibilities:
    - Generate .wsb configuration files
    - Write auth token to the communication folder
    - Launch WindowsSandbox.exe
    - Wait for the shim DLL to become ready (port file)
    - Health monitoring
    - Cleanup on stop
    """

    def __init__(self, dll_folder: str | Path) -> None:
        """
        Args:
            dll_folder: Host path to the folder containing shim DLLs and injector scripts.
                        This is mapped read-only into the sandbox.
        """
        self._dll_folder = Path(dll_folder).resolve()
        if not self._dll_folder.is_dir():
            raise FileNotFoundError(f"DLL folder not found: {self._dll_folder}")

        self._comm_folder: Path | None = None
        self._wsb_path: Path | None = None
        self._process: subprocess.Popen[Any] | None = None
        self._token: str = ""
        self._port: int = 0
        self._ready = False
        self._temp_dir: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, exe_path: str, timeout: float = 30.0) -> bool:
        """Launch a sandbox instance and wait for the shim to be ready.

        Args:
            exe_path: Path to the target executable inside the sandbox.
            timeout: Maximum seconds to wait for shim readiness.

        Returns:
            True if the sandbox launched and shim became ready within *timeout*.
        """
        self.stop()  # clean up any previous instance

        # Create temp directories
        self._temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_shim_"))
        self._comm_folder = self._temp_dir / "comm"
        self._comm_folder.mkdir()

        # Generate auth token
        self._token = os.urandom(_TOKEN_BYTES).hex()
        token_file = self._comm_folder / "auth_token.txt"
        token_file.write_text(self._token, encoding="utf-8")
        logger.info("Auth token written to %s", token_file)

        # Generate .wsb file
        logon_cmd = _DEFAULT_LOGON_CMD.replace("${exe_path}", exe_path)
        wsb_content = _WSB_TEMPLATE.substitute(
            dll_folder=str(self._dll_folder),
            comm_folder=str(self._comm_folder),
            logon_command=logon_cmd,
        )
        self._wsb_path = self._temp_dir / "sandbox.wsb"
        self._wsb_path.write_text(wsb_content, encoding="utf-8")
        logger.info("Generated .wsb config at %s", self._wsb_path)

        # Launch sandbox
        try:
            self._process = subprocess.Popen(
                ["WindowsSandbox.exe", str(self._wsb_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("WindowsSandbox.exe not found — is Windows Sandbox enabled?")
            self._cleanup_temp()
            return False
        except OSError as exc:
            logger.error("Failed to launch WindowsSandbox.exe: %s", exc)
            self._cleanup_temp()
            return False

        logger.info("WindowsSandbox.exe launched (PID %d)", self._process.pid)

        # Wait for shim to write port file
        try:
            self._port = ShimIPCClient.discover_port(self._comm_folder, timeout=timeout)
            self._ready = True
            logger.info("Sandbox shim ready on port %d", self._port)
        except (TimeoutError, ValueError) as exc:
            logger.error("Shim did not become ready within %.1fs: %s", timeout, exc)
            self.stop()
            return False

        # Trigger sandbox adapter registration by importing its module
        try:
            import src.sandbox.adapters.sandbox_shim  # noqa: F401
        except ImportError:
            logger.debug("Sandbox shim adapter module not yet available")

        return True

    def stop(self) -> None:
        """Stop the sandbox and clean up all temporary files."""
        self._ready = False
        self._port = 0
        self._token = ""

        if self._process is not None:
            if self._process.poll() is None:
                logger.info("Terminating sandbox process (PID %d)", self._process.pid)
                try:
                    self._process.terminate()
                    self._process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Sandbox did not terminate gracefully — killing")
                    self._process.kill()
                    self._process.wait(timeout=5)
                except OSError as exc:
                    logger.warning("Error terminating sandbox: %s", exc)
            self._process = None

        self._cleanup_temp()

    def is_ready(self) -> bool:
        """True if the sandbox is running and the shim reported a port."""
        if not self._ready:
            return False
        if self._process is None or self._process.poll() is not None:
            self._ready = False
            return False
        return True

    def is_sandbox_process(self, hwnd: int) -> bool:
        """Check if a window handle belongs to the sandbox process.

        Uses GetWindowThreadProcessId to get the PID and compares against
        the known sandbox process PID.
        """
        if self._process is None:
            return False
        try:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value == self._process.pid
        except Exception:
            return False

    def get_connection_info(self) -> tuple[str, int, str]:
        """Return (host, port, token) for connecting to the shim.

        Raises:
            RuntimeError: If the sandbox is not ready.
        """
        if not self.is_ready():
            raise RuntimeError("Sandbox is not ready")
        return ("127.0.0.1", self._port, self._token)

    @property
    def comm_folder(self) -> Path | None:
        """The communication folder path, or None if not started."""
        return self._comm_folder

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cleanup_temp(self) -> None:
        """Remove temporary directory tree."""
        if self._temp_dir is not None and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                logger.debug("Cleaned up temp dir %s", self._temp_dir)
            except OSError as exc:
                logger.warning("Failed to clean up %s: %s", self._temp_dir, exc)
        self._temp_dir = None
        self._comm_folder = None
        self._wsb_path = None
