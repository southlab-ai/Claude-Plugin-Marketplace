# CV Plugin Setup

Verify and install the Computer Vision plugin dependencies.

1. Check that `uv` is installed: `uv --version`
2. Run `uv sync --directory "${CLAUDE_PLUGIN_ROOT}"` to install all dependencies
3. Verify the MCP server starts: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python -c "from src.server import mcp; print('Server OK:', len(mcp._tool_manager._tools), 'tools registered')"`
4. Check OCR language availability:
   - Run: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python -c "import winocr, asyncio; from PIL import Image; img = Image.new('RGB', (100, 30), 'white'); result = asyncio.run(winocr.recognize_pil(img, lang='en')); print('OCR OK: en')"`
   - If the command above fails, OCR will auto-detect available languages (es, pt, fr, de, etc.)
   - To check which OCR languages are installed run: `powershell -Command "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Select-Object LanguageTag"`
   - To install English OCR (requires elevated PowerShell): `Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"`
   - OCR works with any installed language — English is not required
5. Report the result to the user, including which OCR languages are available
