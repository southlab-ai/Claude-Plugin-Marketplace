# Computer Vision Plugin for Claude Code

Desktop computer vision and input control for Claude Code on Windows. Like Claude-in-Chrome, but for **any Windows application**.

## What It Does

This MCP plugin gives Claude Code the ability to see and interact with any window on your Windows desktop:

- **Screenshot** any window, the full desktop, or a specific screen region — saved to temp files, viewable natively via Read tool
- **List windows** with title, process, position, and monitor info
- **Click** anywhere on screen (left/right/double/middle/drag)
- **Type text** and **send keyboard shortcuts** to any application
- **OCR** — extract text from any window with bounding boxes and confidence scores
- **Find elements** by natural language (like Chrome MCP's `find`, but for any app)
- **Extract text** from any window — UIA for native apps, OCR fallback for Chrome/Electron
- **Read UI trees** via Windows UI Automation (like `read_page` for desktop apps)
- **Multi-monitor** support with DPI awareness
- **Wait** for windows to appear before interacting

## Installation

Inside Claude Code:

```
/plugin marketplace add MasterMind-SL/Marketplace
/plugin install computer-vision@mastermind-marketplace
```

Then restart Claude Code and run `/cv-setup` to verify dependencies.

### Manual (development)

```bash
git clone https://github.com/MasterMind-SL/computer-vision-plugin
cd computer-vision-plugin
uv sync
claude --plugin-dir .
```

## Requirements

- Windows 10 21H2+ or Windows 11
- Python 3.11+
- `uv` package manager
- At least one Windows OCR language pack (see [OCR Language Support](#ocr-language-support))

## Tools Reference

| Tool | Description |
|------|-------------|
| `cv_list_windows` | List all visible windows with HWND, title, process, rect |
| `cv_screenshot_window` | Capture a window — returns `image_path` for native viewing |
| `cv_screenshot_desktop` | Capture the desktop — returns `image_path` for native viewing |
| `cv_screenshot_region` | Capture a region — returns `image_path` for native viewing |
| `cv_focus_window` | Bring a window to the foreground |
| `cv_mouse_click` | Click at screen coordinates (left/right/double/middle/drag) |
| `cv_type_text` | Type text into the foreground window (Unicode) |
| `cv_send_keys` | Send key combinations (Ctrl+S, Alt+Tab, etc.) |
| `cv_move_window` | Move/resize a window or maximize/minimize/restore |
| `cv_ocr` | Extract text from a window or region with bounding boxes and confidence |
| `cv_find` | Find elements by natural language query (UIA + OCR fuzzy search) |
| `cv_get_text` | Extract all visible text from a window (UIA primary, OCR fallback) |
| `cv_list_monitors` | List all monitors with resolution, DPI, and position |
| `cv_read_ui` | Read the UI accessibility tree of a window |
| `cv_wait_for_window` | Wait for a window matching a title pattern to appear |
| `cv_wait` | Simple delay (max 30 seconds) |

## Quick Start

**List windows and take a screenshot:**
1. `cv_list_windows` — see all open windows
2. Find the HWND of your target window
3. `cv_screenshot_window(hwnd=<HWND>)` — get `image_path`
4. Use Read tool on `image_path` — Claude **sees** the window natively

**Click a button in an app:**
1. `cv_screenshot_window` + Read `image_path` — Claude sees the current state
2. Identify button coordinates from what Claude sees
3. `cv_mouse_click(x=<X>, y=<Y>)` — click it
4. `cv_screenshot_window` — verify the click worked

**Find and click an element by description:**
1. `cv_find(query="Submit button", hwnd=<HWND>)` — find element by natural language
2. Click the returned bbox center coordinates with `cv_mouse_click`

**Read text from any app:**
1. `cv_get_text(hwnd=<HWND>)` — extract all text (UIA for native apps, OCR fallback)
2. Or `cv_ocr(hwnd=<HWND>)` — extract text with bounding boxes and word positions

**Automate a workflow:**
1. `cv_list_windows` — find target app
2. `cv_focus_window` — bring it to front
3. `cv_type_text` / `cv_send_keys` — interact
4. `cv_screenshot_window` — verify result

## OCR Language Support

The `cv_ocr` tool uses Windows' built-in OCR engine via `winocr`. It auto-detects installed language packs and prefers `en-US` when available. You can force a specific language with the `lang` parameter.

**Check installed languages:**

```powershell
# PowerShell (no elevation needed)
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Select-Object LanguageTag
```

The plugin caches available languages at first use and prefers English regardless of system locale. Image preprocessing (upscale, grayscale, sharpen, contrast) is enabled by default for better accuracy.

**To install additional languages** (elevated PowerShell):

```powershell
# English
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
# Spanish
Add-WindowsCapability -Online -Name "Language.OCR~~~es-ES~0.0.1.0"
```

After installing a new language pack, restart Claude Code for the MCP server to pick it up.

## Configuration

Environment variables (all optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `CV_RESTRICTED_PROCESSES` | `credential manager,keepass,1password,bitwarden,windows security` | Comma-separated process names blocked from input |
| `CV_DRY_RUN` | `false` | Return planned actions without executing |
| `CV_DEFAULT_MAX_WIDTH` | `1280` | Default screenshot downscale width |
| `CV_MAX_TEXT_LENGTH` | `1000` | Max characters for `cv_type_text` |
| `CV_RATE_LIMIT` | `20` | Max input actions per second |
| `CV_AUDIT_LOG_PATH` | `%LOCALAPPDATA%/claude-cv-plugin/audit.jsonl` | Audit log location |
| `CV_OCR_REDACTION_PATTERNS` | SSN + credit card patterns | Regex patterns to redact from OCR/text output |

## Security

- Runs at **user privilege level** only — no elevation
- **Restricted processes** blocklist prevents interaction with password managers and sensitive apps
- **Rate limiting** (20 actions/sec) prevents runaway automation
- **HWND freshness validation** prevents acting on stale window handles
- **Audit logging** records all input actions to structured JSON log
- **Dry-run mode** lets you preview actions without executing
- **OCR redaction** masks sensitive text patterns in OCR output
- Cannot interact with UAC prompts or credential dialogs

## How Screenshots Work

Screenshot tools **save images to temp files** and return the file path in the JSON response. Claude Code then uses the Read tool on `image_path` to view the image natively as a multimodal LLM.

Each screenshot response contains:
- **`image_path`** — absolute path to the saved PNG file (auto-cleaned after 5 min)
- **`rect`** — window/region position and size in screen pixels
- **`physical_resolution`** / **`logical_resolution`** — for DPI-aware coordinate math
- **`dpi_scale`** — scale factor for the captured window/region

This approach avoids base64 overhead and context window limits, and leverages Claude's native image understanding via the Read tool.

## Architecture

```
src/
├── __main__.py          # Entry point (DPI init + server start)
├── server.py            # FastMCP with auto-registration
├── config.py            # Settings from environment variables
├── errors.py            # Structured error types
├── models.py            # Pydantic models
├── dpi.py               # DPI awareness helpers
├── coordinates.py       # Coordinate transforms
├── tools/               # MCP tool definitions (16 tools)
│   ├── windows.py       # F1, F5, F9
│   ├── capture.py       # F2, F3, F4 (saves to temp file, returns path)
│   ├── input_mouse.py   # F6
│   ├── input_keyboard.py # F7, F8
│   ├── ocr.py           # F10 (delegates to OcrEngine)
│   ├── find.py          # cv_find — natural language element finder
│   ├── text_extract.py  # cv_get_text — clean text extraction
│   ├── monitors.py      # F11
│   ├── accessibility.py # F12
│   └── synchronization.py # F13
└── utils/               # Shared utilities
    ├── screenshot.py     # mss + PrintWindow capture
    ├── win32_input.py    # ctypes SendInput wrappers
    ├── win32_window.py   # pywin32 window management
    ├── security.py       # Security gate + audit log + PII redaction
    ├── uia.py            # UI Automation tree walker
    └── ocr_engine.py     # OcrEngine (language cache, preprocessing, bbox extraction)
```

## Dependencies

- `mcp` — MCP protocol
- `mss` — Fast screen capture (DXGI)
- `pywin32` — Windows API
- `Pillow` — Image processing
- `winocr` — Windows native OCR
- `comtypes` — UI Automation
- `pydantic` — Input validation

## License

MIT
