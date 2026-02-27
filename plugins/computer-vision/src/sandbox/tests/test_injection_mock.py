"""Tests for the DLL injection engine (mocked ctypes/kernel32 calls).

Tests the DllInjector class from src/sandbox/injection/dll_injector.py.
All Win32 API calls are mocked so tests run without admin privileges
or actual sandbox processes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.sandbox.injection.dll_injector import (
    DllInjector,
    InjectionAttempt,
    InjectionResult,
)


@pytest.fixture
def dll_folder(tmp_path: Path) -> Path:
    """Create a temp folder with fake shim DLLs."""
    (tmp_path / "shim32.dll").write_bytes(b"fake32")
    (tmp_path / "shim64.dll").write_bytes(b"fake64")
    return tmp_path


@pytest.fixture
def injector(dll_folder: Path) -> DllInjector:
    """Create a DllInjector instance."""
    return DllInjector(dll_folder=dll_folder)


class TestInjectPrimary:
    """Test the primary injection path: CreateRemoteThread (tier 1)."""

    def test_inject_success_primary(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """CreateRemoteThread succeeds on the first try."""
        tier1_ok = InjectionAttempt(tier=1, method="CreateRemoteThread+LoadLibraryW", success=True)
        with patch.object(injector, "_tier1_remote_thread", return_value=tier1_ok) as mock_t1:
            dll = dll_folder / "shim64.dll"
            result = injector.inject(pid=1234, dll_path=str(dll))
            assert result.success is True
            assert len(result.attempts) == 1
            assert result.attempts[0].success is True
            mock_t1.assert_called_once()


class TestInjectFallbacks:
    """Test the fallback injection strategies."""

    def test_inject_fallback_to_hook(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """Tier 1 fails; tier 2 (SetWindowsHookEx) succeeds."""
        tier1_fail = InjectionAttempt(tier=1, method="CreateRemoteThread+LoadLibraryW", success=False, error="fail")
        tier2_ok = InjectionAttempt(tier=2, method="SetWindowsHookEx(WH_CBT)", success=True)

        with (
            patch.object(injector, "_tier1_remote_thread", return_value=tier1_fail),
            patch.object(injector, "_tier2_windows_hook", return_value=tier2_ok),
        ):
            dll = dll_folder / "shim64.dll"
            result = injector.inject(pid=1234, dll_path=str(dll))
            assert result.success is True
            assert len(result.attempts) == 2
            assert result.attempts[0].success is False
            assert result.attempts[1].success is True

    def test_inject_fallback_to_ifeo(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """Tiers 1 and 2 fail; tier 3 (IFEO) succeeds."""
        tier1_fail = InjectionAttempt(tier=1, method="CreateRemoteThread+LoadLibraryW", success=False, error="fail")
        tier2_fail = InjectionAttempt(tier=2, method="SetWindowsHookEx(WH_CBT)", success=False, error="fail")
        tier3_ok = InjectionAttempt(tier=3, method="IFEO Registry", success=True)

        with (
            patch.object(injector, "_tier1_remote_thread", return_value=tier1_fail),
            patch.object(injector, "_tier2_windows_hook", return_value=tier2_fail),
            patch.object(injector, "_tier3_ifeo", return_value=tier3_ok),
        ):
            dll = dll_folder / "shim64.dll"
            result = injector.inject(pid=1234, dll_path=str(dll))
            assert result.success is True
            assert len(result.attempts) == 3
            assert result.attempts[2].success is True

    def test_inject_all_fail(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """All 3 tiers fail; inject returns success=False."""
        tier1_fail = InjectionAttempt(tier=1, method="CreateRemoteThread+LoadLibraryW", success=False, error="fail")
        tier2_fail = InjectionAttempt(tier=2, method="SetWindowsHookEx(WH_CBT)", success=False, error="fail")
        tier3_fail = InjectionAttempt(tier=3, method="IFEO Registry", success=False, error="fail")

        with (
            patch.object(injector, "_tier1_remote_thread", return_value=tier1_fail),
            patch.object(injector, "_tier2_windows_hook", return_value=tier2_fail),
            patch.object(injector, "_tier3_ifeo", return_value=tier3_fail),
        ):
            dll = dll_folder / "shim64.dll"
            result = injector.inject(pid=1234, dll_path=str(dll))
            assert result.success is False
            assert len(result.attempts) == 3


class TestBitnessDetection:
    """Test 32-bit vs 64-bit DLL auto-selection via _select_dll."""

    def test_bitness_detection_64bit(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """Non-WOW64 process -> selects shim64.dll."""
        with patch.object(DllInjector, "_is_wow64_process", return_value=False):
            selected = injector._select_dll(1234)
            assert selected is not None
            assert selected.name == "shim64.dll"

    def test_bitness_detection_32bit(
        self, injector: DllInjector, dll_folder: Path
    ) -> None:
        """WOW64 process (32-bit on 64-bit OS) -> selects shim32.dll."""
        with patch.object(DllInjector, "_is_wow64_process", return_value=True):
            selected = injector._select_dll(1234)
            assert selected is not None
            assert selected.name == "shim32.dll"


class TestInjectDllNotFound:
    """Test injection when the DLL file does not exist."""

    def test_inject_dll_not_found(self, injector: DllInjector) -> None:
        """Non-existent DLL path -> InjectionResult with failure."""
        result = injector.inject(pid=1234, dll_path="C:\\does_not_exist\\fake.dll")
        assert result.success is False
        assert len(result.attempts) >= 1
        assert "not found" in result.attempts[0].error.lower() or "dll" in result.attempts[0].error.lower()


class TestInjectionResult:
    """Test the InjectionResult and InjectionAttempt dataclasses."""

    def test_injection_result_defaults(self) -> None:
        """InjectionResult defaults to success=False."""
        r = InjectionResult()
        assert r.success is False
        assert r.dll_path == ""
        assert r.target_pid == 0
        assert r.attempts == []

    def test_injection_result_summary(self) -> None:
        """InjectionResult.summary produces readable text."""
        r = InjectionResult(
            success=True,
            dll_path="C:\\shim64.dll",
            target_pid=1234,
            attempts=[
                InjectionAttempt(tier=1, method="CreateRemoteThread+LoadLibraryW", success=True, duration_ms=50.0),
            ],
        )
        summary = r.summary
        assert "1234" in summary
        assert "succeeded" in summary

    def test_injection_attempt_fields(self) -> None:
        """InjectionAttempt captures tier, method, success, error, duration."""
        a = InjectionAttempt(tier=2, method="hook", success=False, error="oops", duration_ms=10.5)
        assert a.tier == 2
        assert a.method == "hook"
        assert a.success is False
        assert a.error == "oops"
        assert a.duration_ms == 10.5
