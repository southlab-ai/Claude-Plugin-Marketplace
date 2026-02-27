"""Unit tests for AdapterRegistry and BaseAdapter."""

from __future__ import annotations

import threading
from unittest.mock import patch, MagicMock

import pytest

from src.adapters import BaseAdapter, AdapterRegistry
from src.models import ActionResult


class DummyAdapter(BaseAdapter):
    """A minimal adapter for testing."""

    def __init__(self):
        self.probe_calls = 0
        self.probe_return = True

    def probe(self, hwnd: int) -> bool:
        self.probe_calls += 1
        return self.probe_return

    def supports_action(self, action: str) -> bool:
        return action in ("invoke",)

    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        return ActionResult(success=True, strategy_used="dummy", layer=0)


class SlowAdapter(BaseAdapter):
    """Adapter with a slow probe for timeout testing."""

    def probe(self, hwnd: int) -> bool:
        import time
        time.sleep(2)
        return True

    def supports_action(self, action: str) -> bool:
        return False

    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        return ActionResult(success=False)


class BrokenAdapter(BaseAdapter):
    """Adapter that raises during probe."""

    def probe(self, hwnd: int) -> bool:
        raise RuntimeError("probe exploded")

    def supports_action(self, action: str) -> bool:
        return False

    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        return ActionResult(success=False)


class FailInitAdapter(BaseAdapter):
    """Adapter that raises during __init__."""

    def __init__(self):
        raise RuntimeError("init exploded")

    def probe(self, hwnd: int) -> bool:
        return True

    def supports_action(self, action: str) -> bool:
        return False

    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        return ActionResult(success=False)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton registry before and after each test."""
    reg = AdapterRegistry()
    reg.reset()
    yield
    reg.reset()


class TestAdapterRegistry:
    """Tests for AdapterRegistry."""

    def test_register_and_get_adapter(self):
        """Register an adapter and retrieve it via matching process name."""
        reg = AdapterRegistry()
        reg.register(["testproc"], DummyAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value="testproc"):
            adapter = reg.get_adapter(12345)
            assert adapter is not None
            assert isinstance(adapter, DummyAdapter)

    def test_get_adapter_returns_none_for_unknown_process(self):
        """get_adapter returns None when process name doesn't match any registered adapter."""
        reg = AdapterRegistry()
        reg.register(["chrome"], DummyAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value="notepad"):
            adapter = reg.get_adapter(12345)
            assert adapter is None

    def test_get_adapter_returns_none_for_empty_process_name(self):
        """get_adapter returns None when process name can't be determined."""
        reg = AdapterRegistry()
        reg.register(["chrome"], DummyAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value=""):
            adapter = reg.get_adapter(12345)
            assert adapter is None

    def test_negative_cache_prevents_repeated_probes(self):
        """After a failed probe, subsequent get_adapter calls should skip probing."""
        reg = AdapterRegistry()

        adapter_cls = DummyAdapter
        reg.register(["failproc"], adapter_cls)

        # Make the probe fail
        with patch.object(AdapterRegistry, "_get_process_name", return_value="failproc"):
            # First: create instance with probe returning False
            with patch.object(DummyAdapter, "probe", return_value=False):
                result1 = reg.get_adapter(12345)
                assert result1 is None

            # Second call: should hit negative cache, never call probe
            with patch.object(DummyAdapter, "probe", return_value=True) as mock_probe:
                result2 = reg.get_adapter(12345)
                assert result2 is None
                mock_probe.assert_not_called()

    def test_graceful_degradation_on_probe_exception(self):
        """If probe raises, get_adapter returns None and logs once."""
        reg = AdapterRegistry()
        reg.register(["broken"], BrokenAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value="broken"):
            adapter = reg.get_adapter(12345)
            assert adapter is None

    def test_graceful_degradation_on_init_failure(self):
        """If adapter __init__ raises, get_adapter returns None."""
        reg = AdapterRegistry()
        reg.register(["failinit"], FailInitAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value="failinit"):
            adapter = reg.get_adapter(12345)
            assert adapter is None

    def test_singleton_pattern(self):
        """AdapterRegistry should be a singleton."""
        reg1 = AdapterRegistry()
        reg2 = AdapterRegistry()
        assert reg1 is reg2

    def test_adapter_instance_caching(self):
        """The same adapter instance should be returned for subsequent calls."""
        reg = AdapterRegistry()
        reg.register(["cached"], DummyAdapter)

        with patch.object(AdapterRegistry, "_get_process_name", return_value="cached"):
            adapter1 = reg.get_adapter(12345)
            adapter2 = reg.get_adapter(12345)
            assert adapter1 is adapter2

    def test_multiple_process_patterns(self):
        """Registering multiple patterns for one adapter class works."""
        reg = AdapterRegistry()
        reg.register(["chrome", "msedge", "brave"], DummyAdapter)

        for proc in ["chrome", "msedge", "brave"]:
            with patch.object(AdapterRegistry, "_get_process_name", return_value=proc):
                # Clear negative cache for each test
                reg._negative_cache.clear()
                adapter = reg.get_adapter(12345)
                assert adapter is not None
                assert isinstance(adapter, DummyAdapter)

    def test_reset_clears_all_state(self):
        """reset() should clear all internal state."""
        reg = AdapterRegistry()
        reg.register(["test"], DummyAdapter)
        reg._negative_cache.add("something")

        reg.reset()

        assert len(reg._pattern_map) == 0
        assert len(reg._adapter_instances) == 0
        assert len(reg._negative_cache) == 0
        assert len(reg._logged_failures) == 0
