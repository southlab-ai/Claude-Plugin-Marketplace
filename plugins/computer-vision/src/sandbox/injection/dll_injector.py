"""DLL injection into sandbox processes via ctypes Win32 API calls.

Implements a 3-tier injection strategy:
  1. CreateRemoteThread + LoadLibraryW (classic)
  2. SetWindowsHookEx with WH_CBT
  3. Image File Execution Options (IFEO) registry key
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Win32 constants
PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_CREATE_THREAD = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WH_CBT = 5

# Timeout per injection tier (ms for WaitForSingleObject, seconds for Python)
_TIER_TIMEOUT_S = 2.0
_WAIT_TIMEOUT_MS = 2000

# Type aliases for readability
HANDLE = ctypes.wintypes.HANDLE
DWORD = ctypes.wintypes.DWORD
LPCWSTR = ctypes.wintypes.LPCWSTR
LPVOID = ctypes.c_void_p
SIZE_T = ctypes.c_size_t
BOOL = ctypes.wintypes.BOOL
HMODULE = ctypes.wintypes.HMODULE
HINSTANCE = ctypes.wintypes.HINSTANCE

# Win32 API
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
advapi32 = ctypes.windll.advapi32


@dataclass
class InjectionAttempt:
    """Result of a single injection tier attempt."""
    tier: int
    method: str
    success: bool
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class InjectionResult:
    """Aggregated result of the full injection pipeline."""
    success: bool = False
    dll_path: str = ""
    target_pid: int = 0
    attempts: list[InjectionAttempt] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines = [f"Injection {'succeeded' if self.success else 'failed'} for PID {self.target_pid}"]
        for a in self.attempts:
            status = "OK" if a.success else f"FAIL ({a.error})"
            lines.append(f"  Tier {a.tier} [{a.method}]: {status} ({a.duration_ms:.0f}ms)")
        return "\n".join(lines)


class DllInjector:
    """Injects a shim DLL into a target process using a 3-tier strategy."""

    def __init__(self, dll_folder: str | Path) -> None:
        """
        Args:
            dll_folder: Folder containing shim32.dll and shim64.dll.
        """
        self._dll_folder = Path(dll_folder).resolve()

    def inject(self, pid: int, dll_path: str | Path | None = None) -> InjectionResult:
        """Inject the shim DLL into the target process.

        Auto-selects shim32.dll vs shim64.dll based on IsWow64Process
        unless *dll_path* is explicitly provided.

        Args:
            pid: Target process ID.
            dll_path: Explicit DLL path. If None, auto-selects from dll_folder.

        Returns:
            InjectionResult with details of all attempts.
        """
        result = InjectionResult(target_pid=pid)

        # Resolve DLL path
        if dll_path is None:
            dll_path = self._select_dll(pid)
            if dll_path is None:
                result.attempts.append(InjectionAttempt(
                    tier=0, method="dll_select", success=False,
                    error="Could not determine target process bitness",
                ))
                return result
        dll_path = Path(dll_path).resolve()
        result.dll_path = str(dll_path)

        if not dll_path.exists():
            result.attempts.append(InjectionAttempt(
                tier=0, method="dll_check", success=False,
                error=f"DLL not found: {dll_path}",
            ))
            return result

        # Tier 1: CreateRemoteThread + LoadLibraryW
        attempt = self._tier1_remote_thread(pid, dll_path)
        result.attempts.append(attempt)
        if attempt.success:
            result.success = True
            logger.info("Tier 1 injection succeeded for PID %d", pid)
            return result

        # Tier 2: SetWindowsHookEx with WH_CBT
        attempt = self._tier2_windows_hook(pid, dll_path)
        result.attempts.append(attempt)
        if attempt.success:
            result.success = True
            logger.info("Tier 2 injection succeeded for PID %d", pid)
            return result

        # Tier 3: IFEO registry key
        attempt = self._tier3_ifeo(pid, dll_path)
        result.attempts.append(attempt)
        if attempt.success:
            result.success = True
            logger.info("Tier 3 injection succeeded for PID %d", pid)
            return result

        logger.error("All injection tiers failed for PID %d", pid)
        return result

    # ------------------------------------------------------------------
    # DLL selection
    # ------------------------------------------------------------------

    def _select_dll(self, pid: int) -> Path | None:
        """Select shim32.dll or shim64.dll based on target process bitness."""
        try:
            is_wow64 = self._is_wow64_process(pid)
        except OSError as exc:
            logger.warning("Could not query process %d bitness: %s", pid, exc)
            return None

        if is_wow64:
            # 32-bit process on 64-bit OS
            dll = self._dll_folder / "shim32.dll"
        else:
            dll = self._dll_folder / "shim64.dll"

        logger.debug("Selected %s for PID %d (wow64=%s)", dll.name, pid, is_wow64)
        return dll

    @staticmethod
    def _is_wow64_process(pid: int) -> bool:
        """Check if a process is running under WOW64 (32-bit on 64-bit OS)."""
        h_process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not h_process:
            raise OSError(f"OpenProcess failed for PID {pid} (error {ctypes.GetLastError()})")
        try:
            result = BOOL()
            ok = kernel32.IsWow64Process(h_process, ctypes.byref(result))
            if not ok:
                raise OSError(f"IsWow64Process failed (error {ctypes.GetLastError()})")
            return bool(result.value)
        finally:
            kernel32.CloseHandle(h_process)

    # ------------------------------------------------------------------
    # Tier 1: CreateRemoteThread + LoadLibraryW
    # ------------------------------------------------------------------

    def _tier1_remote_thread(self, pid: int, dll_path: Path) -> InjectionAttempt:
        """Classic remote thread injection using LoadLibraryW."""
        t0 = time.monotonic()
        method = "CreateRemoteThread+LoadLibraryW"

        h_process = None
        remote_mem = None
        try:
            access = (
                PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION
                | PROCESS_VM_WRITE | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
            )
            h_process = kernel32.OpenProcess(access, False, pid)
            if not h_process:
                return self._attempt(1, method, t0, f"OpenProcess failed ({ctypes.GetLastError()})")

            # Encode DLL path as wide string
            dll_path_str = str(dll_path)
            dll_bytes = (dll_path_str + "\0").encode("utf-16-le")

            # Allocate memory in target process
            remote_mem = kernel32.VirtualAllocEx(
                h_process, None, len(dll_bytes), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
            )
            if not remote_mem:
                return self._attempt(1, method, t0, f"VirtualAllocEx failed ({ctypes.GetLastError()})")

            # Write DLL path
            written = SIZE_T(0)
            ok = kernel32.WriteProcessMemory(
                h_process, remote_mem, dll_bytes, len(dll_bytes), ctypes.byref(written)
            )
            if not ok:
                return self._attempt(1, method, t0, f"WriteProcessMemory failed ({ctypes.GetLastError()})")

            # Get LoadLibraryW address
            h_kernel32 = kernel32.GetModuleHandleW("kernel32.dll")
            if not h_kernel32:
                return self._attempt(1, method, t0, "GetModuleHandleW(kernel32) failed")
            load_library_addr = kernel32.GetProcAddress(h_kernel32, b"LoadLibraryW")
            if not load_library_addr:
                return self._attempt(1, method, t0, "GetProcAddress(LoadLibraryW) failed")

            # Create remote thread
            thread_id = DWORD(0)
            h_thread = kernel32.CreateRemoteThread(
                h_process, None, 0, load_library_addr, remote_mem, 0, ctypes.byref(thread_id)
            )
            if not h_thread:
                return self._attempt(1, method, t0, f"CreateRemoteThread failed ({ctypes.GetLastError()})")

            # Wait for thread to complete
            try:
                wait_result = kernel32.WaitForSingleObject(h_thread, _WAIT_TIMEOUT_MS)
                if wait_result == WAIT_OBJECT_0:
                    return self._attempt(1, method, t0, success=True)
                elif wait_result == WAIT_TIMEOUT:
                    return self._attempt(1, method, t0, "Thread wait timed out")
                else:
                    return self._attempt(1, method, t0, f"WaitForSingleObject returned {wait_result}")
            finally:
                kernel32.CloseHandle(h_thread)

        except Exception as exc:
            return self._attempt(1, method, t0, str(exc))
        finally:
            if remote_mem and h_process:
                kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
            if h_process:
                kernel32.CloseHandle(h_process)

    # ------------------------------------------------------------------
    # Tier 2: SetWindowsHookEx with WH_CBT
    # ------------------------------------------------------------------

    def _tier2_windows_hook(self, pid: int, dll_path: Path) -> InjectionAttempt:
        """Inject via SetWindowsHookEx with WH_CBT hook."""
        t0 = time.monotonic()
        method = "SetWindowsHookEx(WH_CBT)"

        try:
            # Load the DLL in our own process to get the hook proc address
            h_dll = kernel32.LoadLibraryW(str(dll_path))
            if not h_dll:
                return self._attempt(2, method, t0, f"LoadLibraryW failed ({ctypes.GetLastError()})")

            try:
                # The DLL must export a CBTProc function
                hook_proc = kernel32.GetProcAddress(h_dll, b"CBTProc")
                if not hook_proc:
                    return self._attempt(2, method, t0, "DLL does not export CBTProc")

                # Get a thread ID in the target process
                tid = self._get_first_thread_id(pid)
                if tid == 0:
                    return self._attempt(2, method, t0, "No threads found for target PID")

                # Install the hook
                h_hook = user32.SetWindowsHookExW(WH_CBT, hook_proc, h_dll, tid)
                if not h_hook:
                    return self._attempt(
                        2, method, t0, f"SetWindowsHookExW failed ({ctypes.GetLastError()})"
                    )

                # The hook is installed. The DLL is now loaded in the target process.
                # We give a brief moment for the hook to fire, then unhook.
                time.sleep(0.1)
                user32.UnhookWindowsHookEx(h_hook)

                return self._attempt(2, method, t0, success=True)

            finally:
                kernel32.FreeLibrary(h_dll)

        except Exception as exc:
            return self._attempt(2, method, t0, str(exc))

    @staticmethod
    def _get_first_thread_id(pid: int) -> int:
        """Get the first thread ID of a process using CreateToolhelp32Snapshot."""
        TH32CS_SNAPTHREAD = 0x00000004

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", DWORD),
                ("cntUsage", DWORD),
                ("th32ThreadID", DWORD),
                ("th32OwnerProcessID", DWORD),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", DWORD),
            ]

        h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if h_snap == ctypes.wintypes.HANDLE(-1).value:
            return 0

        try:
            te = THREADENTRY32()
            te.dwSize = ctypes.sizeof(THREADENTRY32)

            if not kernel32.Thread32First(h_snap, ctypes.byref(te)):
                return 0

            while True:
                if te.th32OwnerProcessID == pid:
                    return te.th32ThreadID
                if not kernel32.Thread32Next(h_snap, ctypes.byref(te)):
                    break
            return 0
        finally:
            kernel32.CloseHandle(h_snap)

    # ------------------------------------------------------------------
    # Tier 3: IFEO (Image File Execution Options) registry key
    # ------------------------------------------------------------------

    def _tier3_ifeo(self, pid: int, dll_path: Path) -> InjectionAttempt:
        """Set an IFEO debugger registry key for the target process.

        This is a last-resort method that sets a Debugger value in the
        IFEO registry key. The shim DLL includes a verifier provider
        that gets loaded when the IFEO key references it.

        Note: This requires elevated privileges and sets a persistent
        registry key that must be cleaned up.
        """
        t0 = time.monotonic()
        method = "IFEO Registry"

        try:
            # Get the process executable name
            exe_name = self._get_process_exe_name(pid)
            if not exe_name:
                return self._attempt(3, method, t0, "Could not determine process exe name")

            import winreg

            key_path = f"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe_name}"

            try:
                key = winreg.CreateKeyEx(
                    winreg.HKEY_LOCAL_MACHINE,
                    key_path,
                    0,
                    winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
                )
            except PermissionError:
                return self._attempt(3, method, t0, "Insufficient privileges for IFEO registry write")
            except OSError as exc:
                return self._attempt(3, method, t0, f"Registry open failed: {exc}")

            try:
                # Set VerifierDlls value to load our shim
                winreg.SetValueEx(key, "VerifierDlls", 0, winreg.REG_SZ, dll_path.name)
                winreg.SetValueEx(key, "VerifierFlags", 0, winreg.REG_DWORD, 0x80000000)
                winreg.SetValueEx(key, "GlobalFlag", 0, winreg.REG_DWORD, 0x100)

                logger.info("IFEO registry key set for %s (verifier: %s)", exe_name, dll_path.name)
                return self._attempt(3, method, t0, success=True)
            finally:
                winreg.CloseKey(key)

        except Exception as exc:
            return self._attempt(3, method, t0, str(exc))

    @staticmethod
    def _get_process_exe_name(pid: int) -> str:
        """Get the executable filename (e.g. 'notepad.exe') for a PID."""
        MAX_PATH = 260
        h_process = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h_process:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            size = DWORD(MAX_PATH)
            ok = kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size))
            if ok:
                full_path = buf.value
                return Path(full_path).name
            return ""
        finally:
            kernel32.CloseHandle(h_process)

    # ------------------------------------------------------------------
    # Cleanup for IFEO
    # ------------------------------------------------------------------

    @staticmethod
    def cleanup_ifeo(exe_name: str) -> bool:
        """Remove IFEO registry entries set by tier 3 injection.

        Args:
            exe_name: The executable filename (e.g. 'notepad.exe').

        Returns:
            True if cleanup succeeded.
        """
        import winreg
        key_path = f"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe_name}"
        try:
            key = winreg.OpenKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                key_path,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
            )
            for name in ("VerifierDlls", "VerifierFlags", "GlobalFlag"):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            logger.info("Cleaned up IFEO registry entries for %s", exe_name)
            return True
        except Exception as exc:
            logger.warning("IFEO cleanup failed for %s: %s", exe_name, exc)
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attempt(
        tier: int, method: str, t0: float, error: str = "", *, success: bool = False
    ) -> InjectionAttempt:
        elapsed = (time.monotonic() - t0) * 1000
        if not success and error:
            logger.debug("Tier %d [%s] failed (%.0fms): %s", tier, method, elapsed, error)
        return InjectionAttempt(
            tier=tier,
            method=method,
            success=success,
            error=error,
            duration_ms=elapsed,
        )
