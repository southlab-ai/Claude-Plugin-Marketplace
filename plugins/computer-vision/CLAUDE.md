# Computer Vision Plugin for Claude Code

## Overview
This is an MCP plugin that gives Claude Code full computer vision and input control across any Windows application. It provides 22 tools for screenshots, window management, mouse/keyboard input, scrolling, OCR, natural language element finding, text extraction, UI accessibility, scene analysis, human-like mouse movement, and action recording with frame-by-frame replay. All mutating tools return post-action screenshots for see-act-verify automation. Input tools support **background mode** (`background=True`) which uses PostMessage to click, type, and send keys without moving the cursor or stealing focus.

## Desktop Automation Guide

This section describes how to use the tools together as a coordinated system for automating any Windows application. Follow these patterns for reliable, debuggable desktop automation.

### The See-Plan-Act-Verify Loop

Every interaction with a desktop app should follow this cycle:

1. **See**: Take a screenshot (`cv_screenshot_window`) or scene analysis (`cv_scene`)
2. **Plan**: Look at the image with your vision. Identify elements, read text, understand the app state. Use `cv_scene` element coordinates for precise targeting.
3. **Act**: Execute the interaction using `cv_record(action="move_click")` for human-like mouse movement, or `cv_mouse_click` for simple clicks.
4. **Verify**: Review the post-action screenshot or `cv_record` frame log to confirm the action succeeded. If an element shook or nothing changed, the action failed — analyze why before retrying.

### Tool Selection Guide

| Situation | Tool | Why |
|-----------|------|-----|
| First look at a window | `cv_screenshot_window` | Quick visual snapshot |
| Need clickable element coordinates | `cv_scene` | Returns numbered elements with `center_screen` coordinates |
| Click a button/element (standard app) | `cv_mouse_click` | Direct, fast click |
| Click in UWP/WebView/game app | `cv_record(action="move_click")` | Generates real WM_MOUSEMOVE events that UWP apps require |
| Trigger hover state before clicking | `cv_mouse_move` then `cv_mouse_click` | Separate move and click for fine control |
| Debug why a click failed | `cv_record` with `frames_after=5` | Review frame-by-frame what happened |
| Drag and drop | `cv_record(action="drag")` or `cv_mouse_click(start_x=..., start_y=...)` | Smooth drag with intermediate frames |
| Click without disturbing user | `cv_mouse_click(background=True, hwnd=...)` | PostMessage — no cursor movement |
| Read text from a window | `cv_ocr` or `cv_get_text` | OCR with bounding boxes |
| Find a specific UI element by description | `cv_find` | Natural language element search |
| Read accessibility tree | `cv_read_ui` | Structured UI hierarchy |

### Human-Like Mouse Movement

Many Windows apps (especially UWP, WebView, Electron, and games) **ignore clicks that appear without preceding mouse movement**. They expect:
1. `WM_MOUSEMOVE` events as the cursor approaches
2. A brief hover period
3. Then the click

**`cv_record(action="move_click")`** handles this automatically:
- Smoothly moves the cursor from its current position to the target using smoothstep interpolation
- Hovers for 50ms (triggering mouse-enter events)
- Clicks
- Captures screenshots at each phase for debugging

**When to use move_click vs direct click**:
- Standard Win32 apps (Notepad, Explorer, Office): `cv_mouse_click` works fine
- UWP apps (Microsoft Store apps, Solitaire, Calculator): Use `cv_record(action="move_click")`
- WebView/Electron apps: Use `cv_record(action="move_click")`
- Games: Use `cv_record(action="move_click")`
- If a direct click doesn't register: Switch to `cv_record(action="move_click")`

### Using cv_scene for Precise Targeting

Instead of guessing pixel coordinates from screenshots:

1. Call `cv_scene(hwnd=...)` to detect all elements
2. View the annotated image with the Read tool — elements have cyan numbered boxes
3. **Use your vision** to identify what each element is (card values, button labels, icons)
4. Use the `center_screen` coordinates from the element list to click precisely

```
cv_scene result → element #5 at center_screen (1045, 178)
                → cv_record(action="move_click", x=1045, y=178)
```

**Important**: OCR labels in `cv_scene` are useful for text-based UI (buttons, menus, labels) but unreliable on graphical content (playing cards, icons, images). Always visually inspect the annotated screenshot with your multimodal vision to identify elements.

### Debugging Failed Interactions with cv_record Frames

When an action doesn't produce the expected result:

1. Review the **before** frame — was the app in the expected state?
2. Review the **hover** frame — did the cursor reach the right position?
3. Review the **click** frame — did the UI react (highlight, selection)?
4. Review the **after** frames — did the element shake (invalid move)? Did nothing change (missed click)? Did something unexpected happen?

Example frame log:
```
t=  0ms  before           ← app state before action
t=150ms  move_start       ← cursor begins moving
t=500ms  hover (x,y)      ← cursor arrived, hovering
t=600ms  click (x,y)      ← click executed
t=800ms  after +200ms     ← first result frame
t=1000ms after +400ms     ← settling frame
```

### Common Patterns

**Deselect before new action**: If a previous interaction left something selected (yellow highlight), click a neutral area first:
```
cv_record(action="move_click", x=<empty_area_x>, y=<empty_area_y>, ...)
```

**Cycle through cards/items**: Repeatedly click a source (like a stock pile) with short delays between draws.

**Two-step placement**: Some apps require select → click destination. Use two sequential `cv_record(action="move_click")` calls with a short delay between them.

**Coordinate spaces**: When you have pixel coordinates from a screenshot image, use `coordinate_space="window_capture"` to auto-convert to screen coordinates. When you have `center_screen` from `cv_scene`, use the default `screen_absolute`.

### Performance Tips

- Use `frames_before=0, frames_after=0` for fast repeated actions (like drawing multiple cards)
- Use `frames_before=1, frames_after=3` for normal interactions where you need verification
- Use `max_width=800` for smaller frame files when you don't need full resolution
- Use `cv_mouse_click` instead of `cv_record` when you know the app responds to direct clicks (no frame recording overhead)

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
mcp, mss, pywin32, Pillow, winocr, comtypes, pydantic, opencv-python-headless, numpy — all installed via `uv sync`.

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
