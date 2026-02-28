# CV Plugin Setup

Verify and install ALL Computer Vision plugin dependencies, including the native sandbox DLL.

## Phase 1: Python Dependencies

1. Check that `uv` is installed: `uv --version`
2. Run `uv sync --directory "${CLAUDE_PLUGIN_ROOT}"` to install all Python dependencies
3. Verify the MCP server starts: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python -c "from src.server import mcp; print('Server OK:', len(mcp._tool_manager._tools), 'tools registered')"`

## Phase 2: OCR Languages

4. Check which OCR languages are installed:
   - Run: `powershell -Command "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Select-Object LanguageTag"`
   - OCR works with any installed language — English is not required
   - To install English OCR (requires elevated PowerShell): `Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"`

## Phase 3: Sandbox Native DLL (Required for cv_sandbox_* tools)

The sandbox tools need a compiled native DLL (shim32.dll, shim64.dll, injector.exe). This phase ensures the C++ build toolchain is available and compiles them.

5. Check if the native DLL is already built:
   - Check if `${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/build/shim64.dll` exists
   - If it exists, skip to Phase 4 (report results)

6. Check if CMake is available: `where cmake` or `cmake --version`
   - If CMake is found, skip to step 8

7. If CMake is NOT found, install VS Build Tools with C++ and CMake:
   - First check if `winget` is available: `winget --version`
   - Install VS Build Tools: `winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.CMake.Project --includeRecommended"`
   - This installs: MSVC compiler, CMake, Windows SDK — everything needed
   - After installation, refresh PATH. CMake is typically at: `"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"`
   - Verify cmake works after install: `cmake --version`
   - NOTE: This is a large install (~2-3 GB). Ask the user for confirmation before proceeding.

8. Check that Microsoft Detours source is vendored:
   - Check if `${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/vendor/Detours/src/detours.h` exists
   - If NOT found, clone it: `git clone https://github.com/microsoft/Detours.git "${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/vendor/Detours"`
   - If the directory exists but `src/detours.h` is missing (placeholder README only), remove the directory first and re-clone

9. Check that nlohmann/json.hpp is the real library (not a placeholder):
   - Run: `head -1 "${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/vendor/nlohmann/json.hpp"`
   - If the first line contains `#error` or `placeholder`, download the real one:
     `curl -sL -o "${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/vendor/nlohmann/json.hpp" "https://github.com/nlohmann/json/releases/download/v3.11.3/json.hpp"`
   - Verify the download: the first line should start with `//     __ _____ _____ _____`

10. Build the native DLLs:
    - If cmake is not in PATH but VS Build Tools is installed, add it: `export PATH="/c/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin:$PATH"`
    - Run: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python scripts/build_native.py`
    - This compiles shim32.dll, shim64.dll, and injector.exe
    - Verify the output: check that `${CLAUDE_PLUGIN_ROOT}/src/sandbox/native/build/shim64.dll` exists

## Phase 4: Report Results

11. Report a summary table to the user:
    - uv version
    - Python dependencies (installed/failed)
    - MCP Server (OK + tool count, or error)
    - OCR languages available
    - Sandbox DLL (built/skipped/failed)
    - Any warnings or manual steps needed
