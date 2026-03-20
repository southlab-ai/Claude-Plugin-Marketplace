# CV Plugin Setup

Verify and install ALL Computer Vision plugin dependencies.

## Phase 1: Python Dependencies

1. Check that `uv` is installed: `uv --version`
2. Run `uv sync --directory "${CLAUDE_PLUGIN_ROOT}"` to install all Python dependencies
3. Verify the MCP server starts: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python -c "from src.server import mcp; print('Server OK:', len(mcp._tool_manager._tools), 'tools registered')"`

## Phase 2: OCR Languages

4. Check which OCR languages are installed:
   - Run: `powershell -Command "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Select-Object LanguageTag"`
   - OCR works with any installed language — English is not required
   - To install English OCR (requires elevated PowerShell): `Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"`

## Phase 3: Report Results

5. Report a summary table to the user:
   - uv version
   - Python dependencies (installed/failed)
   - MCP Server (OK + tool count, or error)
   - OCR languages available
   - Any warnings or manual steps needed
