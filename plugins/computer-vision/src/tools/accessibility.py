"""MCP tool for reading UI Automation accessibility trees."""

from __future__ import annotations

import logging

import ctypes

from src.server import mcp
from src.errors import UIA_ERROR, make_error, make_success
from src import config
from src.utils.security import validate_hwnd_fresh, check_restricted, log_action

logger = logging.getLogger(__name__)

# Interactive control type IDs for filtering
_INTERACTIVE_TYPES = {
    50000,  # Button
    50002,  # CheckBox
    50003,  # ComboBox
    50004,  # Edit
    50005,  # Hyperlink
    50007,  # ListItem
    50011,  # MenuItem
    50013,  # RadioButton
    50015,  # Slider
    50019,  # TabItem
    50031,  # SplitButton
}


def _get_process_name_from_hwnd(hwnd: int) -> str:
    """Get the process name for a window handle."""
    try:
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""

        from src.utils.security import get_process_name_by_pid
        return get_process_name_by_pid(pid.value)
    except Exception:
        return ""


@mcp.tool()
def cv_read_ui(
    hwnd: int,
    depth: int = 5,
    filter: str = "all",
    mode: str = "flat",
) -> dict:
    """Read all UI elements in a window via UI Automation.

    **Default mode (flat)**: Uses ``FindAll(TreeScope_Descendants)`` to discover
    ALL elements in a single fast COM call with no depth limit. This finds deeply
    nested elements (like WinUI 3 toolbar buttons) that the tree walker misses.

    **Tree mode**: Uses ``TreeWalker`` to preserve parent-child hierarchy, limited
    by ``depth``. Useful when you need to understand UI structure.

    Use ``cv_click_ui`` to programmatically click elements found here —
    it works on WinUI 3 apps where ``cv_mouse_click`` fails.

    Args:
        hwnd: Window handle to inspect.
        depth: Maximum tree depth (only used in ``mode="tree"``). Default 5.
        filter: "all" for all elements, "interactive" for only buttons,
                edits, combos, checkboxes, menu items, sliders, tabs.
        mode: "flat" (default, fast, complete) or "tree" (hierarchical, depth-limited).
    """
    # Validate hwnd is still alive
    if not validate_hwnd_fresh(hwnd):
        return make_error(UIA_ERROR, f"Window handle {hwnd} is no longer valid")

    # Security gate: check process restriction
    process_name = _get_process_name_from_hwnd(hwnd)
    try:
        check_restricted(process_name)
    except Exception as exc:
        log_action("cv_read_ui", {"hwnd": hwnd}, "ACCESS_DENIED")
        return make_error(UIA_ERROR, str(exc))

    if filter not in ("all", "interactive"):
        return make_error(UIA_ERROR, f"Invalid filter '{filter}'. Must be 'all' or 'interactive'.")

    if mode not in ("flat", "tree"):
        return make_error(UIA_ERROR, f"Invalid mode '{mode}'. Must be 'flat' or 'tree'.")

    try:
        if mode == "flat":
            return _read_flat(hwnd, filter)
        else:
            return _read_tree(hwnd, depth, filter)
    except TimeoutError as exc:
        log_action("cv_read_ui", {"hwnd": hwnd}, "TIMEOUT")
        return make_error(UIA_ERROR, str(exc))
    except Exception as exc:
        log_action("cv_read_ui", {"hwnd": hwnd}, "ERROR")
        return make_error(UIA_ERROR, f"COM error reading UI tree: {exc}")


def _read_flat(hwnd: int, filter: str) -> dict:
    """Read all elements using FindAll (flat, fast, no depth limit)."""
    from src.utils.uia_click import find_all_elements, CONTROL_TYPE_NAMES

    interactive_only = filter == "interactive"
    raw = find_all_elements(hwnd)

    elements = []
    for i, el in enumerate(raw):
        if interactive_only and el["control_type_id"] not in _INTERACTIVE_TYPES:
            continue

        elements.append({
            "ref_id": f"ref_{i + 1}",
            "name": el["name"],
            "control_type": el["control_type"],
            "rect": el["rect"],
            "automation_id": el["automation_id"],
            "is_interactive": el["control_type_id"] in _INTERACTIVE_TYPES,
        })

    log_action("cv_read_ui", {"hwnd": hwnd, "mode": "flat", "filter": filter}, "OK")
    return make_success(elements=elements, count=len(elements))


def _read_tree(hwnd: int, depth: int, filter: str) -> dict:
    """Read elements using TreeWalker (hierarchical, depth-limited)."""
    from src.utils.uia import get_ui_tree

    if depth < 1:
        depth = 1
    elif depth > config.DEFAULT_UIA_DEPTH * 2:
        depth = config.DEFAULT_UIA_DEPTH * 2

    elements = get_ui_tree(hwnd, depth=depth, filter=filter)
    serialized = [elem.model_dump() for elem in elements]
    log_action("cv_read_ui", {"hwnd": hwnd, "mode": "tree", "depth": depth, "filter": filter}, "OK")
    return make_success(elements=serialized, count=len(serialized))
