"""Adapter registry and base adapter ABC for application-specific automation."""

from __future__ import annotations

import abc
import ctypes
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import ActionResult

logger = logging.getLogger(__name__)


class BaseAdapter(abc.ABC):
    """Abstract base class for application-specific adapters."""

    @abc.abstractmethod
    def probe(self, hwnd: int) -> bool:
        """Return True if this adapter can handle the given window.

        Must return within 500ms.
        """

    @abc.abstractmethod
    def supports_action(self, action: str) -> bool:
        """Return True if this adapter supports the given action name."""

    @abc.abstractmethod
    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        """Execute an action on the given window/target.

        Args:
            hwnd: Window handle.
            target: Target selector (CSS selector, cell reference, path, etc.).
            action: Action name (invoke, set_value, get_value, get_text, etc.).
            value: Optional value for set operations.

        Returns:
            ActionResult describing the outcome.
        """


# Mapping from module path to the adapter class name within it
_ADAPTER_MODULES: dict[str, str] = {
    "src.adapters.chrome_cdp": "ChromeCDPAdapter",
    "src.adapters.office_com": "OfficeCOMAdapter",
    "src.adapters.shell_com": "ShellCOMAdapter",
}


class AdapterRegistry:
    """Singleton registry that maps process names to adapters with lazy loading."""

    _instance: AdapterRegistry | None = None
    _lock = threading.Lock()

    def __new__(cls) -> AdapterRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._pattern_map: dict[str, type] = {}
                    inst._adapter_instances: dict[type, BaseAdapter] = {}
                    inst._negative_cache: set[str] = set()
                    inst._logged_failures: set[str] = set()
                    cls._instance = inst
        return cls._instance

    def register(self, process_patterns: list[str], adapter_cls: type) -> None:
        """Register an adapter class for a list of process name patterns.

        Args:
            process_patterns: Lowercase process names (without .exe) that this adapter handles.
            adapter_cls: The adapter class (must be a subclass of BaseAdapter).
        """
        for pattern in process_patterns:
            self._pattern_map[pattern.lower()] = adapter_cls

    def get_adapter(self, hwnd: int) -> BaseAdapter | None:
        """Find and return an adapter instance for the given window handle.

        Checks the process name of the window, looks up registered adapters,
        probes the matching adapter, and caches negative results.

        Returns None if no adapter matches or probe fails.
        """
        process_name = self._get_process_name(hwnd)
        if not process_name:
            return None

        # Check negative cache
        if process_name in self._negative_cache:
            return None

        adapter_cls = self._pattern_map.get(process_name)
        if adapter_cls is None:
            return None

        # Get or create adapter instance
        adapter = self._adapter_instances.get(adapter_cls)
        if adapter is None:
            try:
                adapter = adapter_cls()
                self._adapter_instances[adapter_cls] = adapter
            except Exception as exc:
                cls_name = adapter_cls.__name__
                if cls_name not in self._logged_failures:
                    logger.info("Failed to instantiate adapter %s: %s", cls_name, exc)
                    self._logged_failures.add(cls_name)
                self._negative_cache.add(process_name)
                return None

        # Probe the adapter
        try:
            if adapter.probe(hwnd):
                return adapter
        except Exception as exc:
            cls_name = adapter_cls.__name__
            if cls_name not in self._logged_failures:
                logger.info("Adapter %s probe failed: %s", cls_name, exc)
                self._logged_failures.add(cls_name)

        # Cache negative probe result for this process name
        self._negative_cache.add(process_name)
        return None

    def reset(self) -> None:
        """Reset the registry state. Useful for testing."""
        self._pattern_map.clear()
        self._adapter_instances.clear()
        self._negative_cache.clear()
        self._logged_failures.clear()

    @staticmethod
    def _get_process_name(hwnd: int) -> str:
        """Get the lowercase process name (without .exe) for a window handle."""
        try:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return ""
            from src.utils.security import get_process_name_by_pid
            return get_process_name_by_pid(pid.value)
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Lazy adapter loading & convenience function
# ---------------------------------------------------------------------------

_adapters_loaded = False


def _load_adapters() -> None:
    """Import all adapter submodules so they self-register with AdapterRegistry."""
    global _adapters_loaded
    if _adapters_loaded:
        return
    _adapters_loaded = True
    for module_path in _ADAPTER_MODULES:
        try:
            __import__(module_path)
        except Exception as exc:
            logger.debug("Failed to load adapter %s: %s", module_path, exc)


def get_adapter(hwnd: int) -> BaseAdapter | None:
    """Convenience: load adapters (once) and query the registry for hwnd."""
    _load_adapters()
    return AdapterRegistry().get_adapter(hwnd)
