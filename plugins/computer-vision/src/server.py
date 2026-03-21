"""FastMCP server instance and auto-registration of tool modules."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Create the shared FastMCP instance — tool modules import this and use @mcp.tool()
#
# The `instructions` field is injected into Claude's system prompt for every
# conversation where this plugin is active.  Keep it short and actionable —
# this is a usage guide, not developer documentation.
mcp = FastMCP("computer-vision", instructions="""\
Desktop vision and input control for any Windows application. 24 tools.

## Quick Start
1. `cv_list_windows` → find the window hwnd
2. `cv_screenshot_window(hwnd)` → see the app (use Read tool on image_path)
3. Act on what you see with the right tool (see table below)

## Tool Selection — Which Tool for What

| Situation | Tool |
|-----------|------|
| See the app | `cv_screenshot_window` |
| Get clickable element coordinates | `cv_scene` — returns numbered elements with `center_screen` |
| Click a button in Win32 apps | `cv_mouse_click` |
| Click in UWP/WebView/game apps | `cv_record(action="move_click")` — smooth mouse with WM_MOUSEMOVE |
| Click WinUI 3 toolbar buttons (Paint, Calculator) | `cv_click_ui(hwnd, name="...")` — UIA patterns, bypasses SendInput |
| List all UI elements by name | `cv_read_ui(mode="flat", filter="interactive")` |
| Draw, drag, game interaction | `cv_record(action="drag")` or `cv_mouse_click(start_x=..., start_y=...)` |
| Click without disturbing user | `cv_mouse_click(background=True, hwnd=...)` — PostMessage |
| Type text | `cv_type_text` |
| Send keyboard shortcut | `cv_send_keys(keys="ctrl+s")` |
| Read text from screen | `cv_ocr` or `cv_get_text` |
| Find element by description | `cv_find` |
| Debug why a click failed | `cv_record` with `frames_after=5` — review frame-by-frame |

## Critical Rules

1. **You are a multimodal LLM** — use the Read tool on screenshots to see the app. Read card values, button labels, and UI state with your vision. Don't rely only on OCR labels.
2. **WinUI 3 apps** (Paint, Calculator, Store apps): `SendInput` clicks are IGNORED on toolbar buttons. Use `cv_click_ui` for toolbars, `cv_mouse_click`/`cv_record` only for canvas areas.
3. **UWP/WebView apps** (Solitaire, Electron): Use `cv_record(action="move_click")` — these apps need real WM_MOUSEMOVE events before accepting clicks.
4. **Verify actions**: After clicking, take a screenshot to confirm it worked. If an element shook or nothing changed, analyze why before retrying.
5. **cv_scene for coordinates**: Don't guess pixel positions. Call `cv_scene(hwnd)` to get precise `center_screen` coordinates for each detected element.

## Delegating to a Body Agent

When a task needs **3+ actions with screenshot verification** (games, multi-step UI flows), delegate to a cheaper subagent:

```
Agent tool: model="sonnet", mode="bypassPermissions"
Prompt (keep it SHORT — every extra word costs tokens):

  BODY AGENT. Concise responses only.
  hwnd=XXXX. Current score=YYY.
  1. cv_record move_click x=AAA y=BBB hwnd=XXXX frames_before=0 frames_after=0 move_duration_ms=250 move_steps=20
  2. cv_wait seconds=0.5
  3. cv_screenshot_window hwnd=XXXX max_width=800
  4. Read screenshot. Report ONLY: new score, what changed, path.
  If action fails: retry at y+20 and y-20. After 3 failures, report what you see.
```

Rules: YOU (Brain) decide what to click and give exact coordinates. The Body only executes and verifies. Never delegate strategy. Combine actions that don't need intermediate verification into a single Bash call.
""")


def _register_tools() -> None:
    """Auto-discover and import all tool modules from src.tools package.

    Each tool module defines functions decorated with @mcp.tool() that
    reference the shared `mcp` instance from this module. Importing them
    is sufficient to register the tools.
    """
    import src.tools as tools_package

    for _importer, module_name, _is_pkg in pkgutil.iter_modules(tools_package.__path__):
        full_name = f"src.tools.{module_name}"
        try:
            importlib.import_module(full_name)
            logger.info("Registered tools from %s", full_name)
        except Exception as e:
            logger.error("Failed to load tool module %s: %s", full_name, e)


# Register all tools on import
_register_tools()
