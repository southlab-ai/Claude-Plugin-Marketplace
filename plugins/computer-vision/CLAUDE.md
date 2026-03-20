# Computer Vision Plugin for Claude Code

## Overview
This is an MCP plugin that gives Claude Code full computer vision and input control across any Windows application. It provides 19 tools for screenshots, window management, mouse/keyboard input, scrolling, OCR, natural language element finding, text extraction, UI accessibility, and multi-monitor support. All mutating tools return post-action screenshots for see-act-verify automation. Input tools support **background mode** (`background=True`) which uses PostMessage to click, type, and send keys without moving the cursor or stealing focus.

## Architecture
- **MCP server**: FastMCP over stdio transport (never HTTP/SSE)
- **Entry point**: `python -m src` → `src/__main__.py` → DPI init → server start
- **Tool registration**: Auto-discovered from `src/tools/` — never edit `server.py` to add tools
- **Tool prefix**: All tools start with `cv_`

## Coding Conventions
- **Models**: Use Pydantic `BaseModel` for all data models (not dataclasses)
- **Errors**: Use `make_error(code, message)` and `make_success(**payload)` from `src/errors.py` for non-image tools
- **Security**: All mutating tools must call security gate before execution:
  1. `validate_hwnd_range(hwnd)` — check HWND in valid Win32 range
  2. `validate_hwnd_fresh(hwnd)` — check window still exists
  3. `check_restricted(process_name)` — block restricted processes
  4. `check_rate_limit()` — enforce rate limit
  5. `guard_dry_run(tool, params)` — return early if dry-run
  6. `log_action(tool, params, status)` — audit log
- **Shared helpers**: `src/utils/action_helpers.py` provides `_capture_post_action()`, `_build_window_state()`, `_get_hwnd_process_name()` — used by all mutating tools for post-action screenshots and window state metadata.
- **Security (read-only tools)**: `cv_ocr`, `cv_find`, `cv_get_text`, `cv_read_ui` use subset: `validate_hwnd_range` + `validate_hwnd_fresh` + `check_restricted` + `log_action` (no rate limit or dry-run).
- **Coordinates**: Screen-absolute physical pixels by default. DPI awareness set at startup. Three coordinate spaces: `screen_absolute` (default), `window_relative` (client area), `window_capture` (pixel coords from a `cv_screenshot_window` image — auto-converts via window rect).
- **Screenshots**: Save images to temp files (`%TEMP%/cv_plugin_screenshots/`) and return `image_path` in the JSON response. Claude uses the `Read` tool on `image_path` to view images natively as a multimodal LLM. Files auto-clean after 5 minutes. Use `capture_window_raw()` / `capture_region_raw()` internally for OCR to avoid file round-trips. `cv_screenshot_window` returns `image_to_screen: {x, y, scale}` — to click at image pixel `(px, py)`, use `screen_x = image_to_screen.x + px`, `screen_y = image_to_screen.y + py` (or use `coordinate_space="window_capture"`). **Grid overlay**: pass `grid=True` to overlay a labeled coordinate grid on the screenshot — labels show `window_capture` coordinates that can be passed directly to `cv_mouse_click(coordinate_space="window_capture")`.
- **Imports**: Tool files import `mcp` from `src.server`, NOT create their own FastMCP instance.

## Testing
- Unit tests in `tests/unit/` with mocked Win32 APIs
- Integration tests in `tests/integration/` require real Windows desktop
- Run: `uv run python -m pytest tests/unit/ -v`

## OCR
- `cv_ocr` auto-detects installed Windows OCR languages via `OcrEngine` singleton in `src/utils/ocr_engine.py`.
- Language preference: `en-US` > `en-*` > other installed. Callers can force a language with `lang` parameter.
- Image preprocessing (enabled by default): upscale small images, grayscale, sharpen, auto-contrast.
- Bounding boxes extracted from `word.bounding_rect` on winocr word objects. Origin offset translates to screen-absolute.
- Pytesseract is a secondary fallback if `winocr` is unavailable.
- Default PII redaction patterns (SSN, credit card) applied to all OCR/text output.

## Background Mode
Input tools (`cv_mouse_click`, `cv_type_text`, `cv_send_keys`) accept `background=True` + `hwnd` to operate without disturbing the user:
- **Mouse**: `PostMessage(WM_LBUTTONDOWN/UP)` — no cursor movement, no focus steal
- **Keyboard**: `PostMessage(WM_CHAR/WM_KEYDOWN)` — no focus required
- **Screenshots**: `PrintWindow` already captures any window regardless of focus
- Coordinates are auto-converted from screen-absolute to client-relative for PostMessage
- Same security gates apply (HWND validation, process restriction, rate limiting)
- Limitation: drag operations are not supported in background mode
- Limitation: some apps (DirectX games, certain UWP controls) may not respond to posted messages

## Dependencies
mcp, mss, pywin32, Pillow, winocr, comtypes, pydantic — all installed via `uv sync`.

## Distribution

The plugin marketplace repo is `southlab-ai/Claude-Plugin-Marketplace`. Install command:
```
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
/plugin install computer-vision@southlab-marketplace
```

For development:
```bash
claude --plugin-dir /path/to/computer-vision-plugin
```
