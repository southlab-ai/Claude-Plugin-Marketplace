// ==========================================================================
// injector/main.cpp - Standalone DLL injector for the Sandbox Shim
// ==========================================================================
// Usage: injector.exe <process_name> <dll_path>
//
// Finds the target process by name, opens it, allocates memory for the DLL
// path, writes it, then creates a remote thread calling LoadLibraryW.
//
// Exit codes:
//   0 - Success
//   1 - Invalid arguments
//   2 - Process not found
//   3 - Failed to open process
//   4 - Failed to allocate memory in target
//   5 - Failed to write DLL path to target
//   6 - Failed to create remote thread
//   7 - Remote thread returned failure
//   8 - DLL path does not exist
// ==========================================================================

#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <string>

// ---------------------------------------------------------------------------
// Exit codes
// ---------------------------------------------------------------------------

static constexpr int EXIT_OK               = 0;
static constexpr int EXIT_BAD_ARGS         = 1;
static constexpr int EXIT_PROC_NOT_FOUND   = 2;
static constexpr int EXIT_OPEN_FAILED      = 3;
static constexpr int EXIT_ALLOC_FAILED     = 4;
static constexpr int EXIT_WRITE_FAILED     = 5;
static constexpr int EXIT_THREAD_FAILED    = 6;
static constexpr int EXIT_THREAD_RETURNED_FAIL = 7;
static constexpr int EXIT_DLL_NOT_FOUND    = 8;

// ---------------------------------------------------------------------------
// Find process by name
// ---------------------------------------------------------------------------

static DWORD find_process_by_name(const wchar_t* process_name) {
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;

    PROCESSENTRY32W pe = {};
    pe.dwSize = sizeof(pe);

    DWORD pid = 0;
    if (Process32FirstW(snapshot, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, process_name) == 0) {
                pid = pe.th32ProcessID;
                break;
            }
        } while (Process32NextW(snapshot, &pe));
    }

    CloseHandle(snapshot);
    return pid;
}

// ---------------------------------------------------------------------------
// Inject DLL via CreateRemoteThread + LoadLibraryW
// ---------------------------------------------------------------------------

static int inject_dll(DWORD pid, const wchar_t* dll_path) {
    // Open the target process
    HANDLE hProcess = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION |
        PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION,
        FALSE, pid);

    if (!hProcess) {
        fprintf(stderr, "[Injector] Failed to open process %lu (error %lu)\n",
                pid, GetLastError());
        return EXIT_OPEN_FAILED;
    }

    // Calculate the size of the DLL path string in bytes (including null terminator)
    size_t path_size_bytes = (wcslen(dll_path) + 1) * sizeof(wchar_t);

    // Allocate memory in the target process for the DLL path
    LPVOID remote_mem = VirtualAllocEx(
        hProcess, nullptr, path_size_bytes,
        MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);

    if (!remote_mem) {
        fprintf(stderr, "[Injector] VirtualAllocEx failed (error %lu)\n", GetLastError());
        CloseHandle(hProcess);
        return EXIT_ALLOC_FAILED;
    }

    // Write the DLL path into the allocated memory
    SIZE_T bytes_written = 0;
    BOOL write_ok = WriteProcessMemory(
        hProcess, remote_mem, dll_path, path_size_bytes, &bytes_written);

    if (!write_ok || bytes_written != path_size_bytes) {
        fprintf(stderr, "[Injector] WriteProcessMemory failed (error %lu)\n", GetLastError());
        VirtualFreeEx(hProcess, remote_mem, 0, MEM_RELEASE);
        CloseHandle(hProcess);
        return EXIT_WRITE_FAILED;
    }

    // Get the address of LoadLibraryW in kernel32.dll
    // This works because kernel32.dll is mapped at the same address in all processes
    HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
    FARPROC pLoadLibraryW = GetProcAddress(hKernel32, "LoadLibraryW");

    // Create a remote thread in the target process that calls LoadLibraryW
    HANDLE hThread = CreateRemoteThread(
        hProcess, nullptr, 0,
        reinterpret_cast<LPTHREAD_START_ROUTINE>(pLoadLibraryW),
        remote_mem, 0, nullptr);

    if (!hThread) {
        fprintf(stderr, "[Injector] CreateRemoteThread failed (error %lu)\n", GetLastError());
        VirtualFreeEx(hProcess, remote_mem, 0, MEM_RELEASE);
        CloseHandle(hProcess);
        return EXIT_THREAD_FAILED;
    }

    // Wait for the remote thread to complete
    WaitForSingleObject(hThread, 10000); // 10 second timeout

    // Check the return value (LoadLibraryW returns HMODULE, 0 = failure)
    DWORD exit_code = 0;
    GetExitCodeThread(hThread, &exit_code);

    // Cleanup
    CloseHandle(hThread);
    VirtualFreeEx(hProcess, remote_mem, 0, MEM_RELEASE);
    CloseHandle(hProcess);

    if (exit_code == 0) {
        fprintf(stderr, "[Injector] LoadLibraryW returned NULL in target process\n");
        return EXIT_THREAD_RETURNED_FAIL;
    }

    return EXIT_OK;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int wmain(int argc, wchar_t* argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: injector.exe <process_name> <dll_path>\n");
        fprintf(stderr, "Example: injector.exe notepad.exe C:\\path\\to\\shim64.dll\n");
        return EXIT_BAD_ARGS;
    }

    const wchar_t* process_name = argv[1];
    const wchar_t* dll_path     = argv[2];

    // Verify the DLL file exists
    DWORD attrs = GetFileAttributesW(dll_path);
    if (attrs == INVALID_FILE_ATTRIBUTES || (attrs & FILE_ATTRIBUTE_DIRECTORY)) {
        fprintf(stderr, "[Injector] DLL not found: %ls\n", dll_path);
        return EXIT_DLL_NOT_FOUND;
    }

    // Resolve to full path
    wchar_t full_path[MAX_PATH] = {};
    DWORD path_len = GetFullPathNameW(dll_path, MAX_PATH, full_path, nullptr);
    if (path_len == 0 || path_len >= MAX_PATH) {
        fprintf(stderr, "[Injector] Failed to resolve DLL path\n");
        return EXIT_DLL_NOT_FOUND;
    }

    // Find the target process
    printf("[Injector] Looking for process: %ls\n", process_name);
    DWORD pid = find_process_by_name(process_name);
    if (pid == 0) {
        fprintf(stderr, "[Injector] Process not found: %ls\n", process_name);
        return EXIT_PROC_NOT_FOUND;
    }

    printf("[Injector] Found process %ls (PID %lu)\n", process_name, pid);
    printf("[Injector] Injecting DLL: %ls\n", full_path);

    // Inject
    int result = inject_dll(pid, full_path);
    if (result == EXIT_OK) {
        printf("[Injector] DLL injected successfully\n");
    } else {
        fprintf(stderr, "[Injector] Injection failed with code %d\n", result);
    }

    return result;
}
