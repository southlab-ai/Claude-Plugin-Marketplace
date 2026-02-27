"""Shell COM adapter for Windows Explorer folder navigation."""

from __future__ import annotations

import ctypes
import logging
import os
import re
from typing import Any

from src.adapters import BaseAdapter, AdapterRegistry
from src.models import ActionResult, VerificationResult

logger = logging.getLogger(__name__)

# Sensitive path patterns to block
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[/\\]\.ssh($|[/\\])", re.IGNORECASE),
    re.compile(r"[/\\]\.gnupg($|[/\\])", re.IGNORECASE),
    re.compile(r"Vault", re.IGNORECASE),
]

# Expected window class for Explorer file browser windows
_EXPLORER_CLASS = "CabinetWClass"


class ShellCOMAdapter(BaseAdapter):
    """Adapter for Windows Explorer via IShellWindows COM interface."""

    def probe(self, hwnd: int) -> bool:
        """Check if hwnd belongs to explorer.exe with CabinetWClass window class."""
        try:
            # Check window class
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
            class_name = buf.value

            if class_name != _EXPLORER_CLASS:
                return False

            # Check process name
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return False

            from src.utils.security import get_process_name_by_pid
            process_name = get_process_name_by_pid(pid.value)
            return process_name == "explorer"

        except Exception as exc:
            logger.debug("ShellCOMAdapter probe failed: %s", exc)
            return False

    def supports_action(self, action: str) -> bool:
        """Supported actions: invoke (navigate), get_value (current path)."""
        return action in ("invoke", "get_value")

    def execute(
        self, hwnd: int, target: str, action: str, value: str | None
    ) -> ActionResult:
        """Execute a shell action.

        Args:
            hwnd: Explorer window handle.
            target: Path for navigation or empty for current path query.
            action: invoke (navigate) or get_value (read current path).
            value: Not used.
        """
        if not self.supports_action(action):
            return ActionResult(
                success=False,
                strategy_used="adapter_shell_com",
                layer=0,
            )

        try:
            if action == "get_value":
                return self._get_current_path(hwnd)
            elif action == "invoke":
                return self._navigate(hwnd, target)
            else:
                return ActionResult(
                    success=False, strategy_used="adapter_shell_com", layer=0
                )
        except Exception as exc:
            logger.warning("ShellCOMAdapter.execute failed: %s", exc)
            return ActionResult(
                success=False,
                strategy_used="adapter_shell_com",
                layer=0,
            )

    def _get_current_path(self, hwnd: int) -> ActionResult:
        """Get the current folder path of an Explorer window via IShellWindows."""
        try:
            import win32com.client

            shell = win32com.client.Dispatch("Shell.Application")
            windows = shell.Windows()

            for i in range(windows.Count):
                try:
                    window = windows.Item(i)
                    if window is None:
                        continue
                    if window.HWND == hwnd:
                        current_path = window.LocationURL or ""
                        # Convert file:/// URL to path
                        if current_path.startswith("file:///"):
                            current_path = current_path[8:].replace("/", "\\")
                            # URL decode
                            from urllib.parse import unquote
                            current_path = unquote(current_path)

                        # Also try LocationName for display name
                        location_name = window.LocationName or ""

                        return ActionResult(
                            success=True,
                            strategy_used="adapter_shell_com",
                            layer=0,
                            verification=VerificationResult(
                                method="none", passed=True
                            ),
                            element={
                                "path": current_path,
                                "name": location_name,
                            },
                        )
                except Exception:
                    continue

            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )
        except ImportError:
            logger.info("win32com not available for ShellCOMAdapter")
            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )
        except Exception as exc:
            logger.debug("ShellCOM get_current_path failed: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )

    def _navigate(self, hwnd: int, target: str) -> ActionResult:
        """Navigate an Explorer window to a new path."""
        try:
            # Expand environment variables
            expanded = os.path.expandvars(target)

            # Check against sensitive paths
            if self._is_sensitive_path(expanded):
                logger.warning("Blocked navigation to sensitive path: %s", target)
                return ActionResult(
                    success=False,
                    strategy_used="adapter_shell_com",
                    layer=0,
                )

            import win32com.client

            shell = win32com.client.Dispatch("Shell.Application")
            windows = shell.Windows()

            for i in range(windows.Count):
                try:
                    window = windows.Item(i)
                    if window is None:
                        continue
                    if window.HWND == hwnd:
                        window.Navigate(expanded)
                        return ActionResult(
                            success=True,
                            strategy_used="adapter_shell_com",
                            layer=0,
                            verification=VerificationResult(
                                method="none", passed=True
                            ),
                            element={"navigated_to": expanded},
                        )
                except Exception:
                    continue

            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )
        except ImportError:
            logger.info("win32com not available for ShellCOMAdapter")
            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )
        except Exception as exc:
            logger.debug("ShellCOM navigate failed: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_shell_com", layer=0
            )

    @staticmethod
    def _is_sensitive_path(path: str) -> bool:
        """Check if a path matches any sensitive path pattern."""
        # Expand common sensitive locations
        appdata = os.environ.get("APPDATA", "")
        sensitive_dirs = []
        if appdata:
            sensitive_dirs.append(os.path.join(appdata, "Vault"))

        for sensitive in sensitive_dirs:
            if sensitive and path.lower().startswith(sensitive.lower()):
                return True

        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(path):
                return True

        return False


# Register with the AdapterRegistry
AdapterRegistry().register(
    ["explorer"],
    ShellCOMAdapter,
)
