"""MCP tool for reading UI Automation accessibility trees."""

from __future__ import annotations

import logging

import ctypes

from src.server import mcp
from src.errors import UIA_ERROR, make_error, make_success
from src import config
from src.utils.security import validate_hwnd_fresh, check_restricted, log_action
from src.utils.uia import get_ui_tree

logger = logging.getLogger(__name__)


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
def cv_read_ui(hwnd: int, depth: int = 5, filter: str = "all") -> dict:
    """Read the UI Automation accessibility tree of a window.

    Walks the UIA element tree for the specified window, returning a structured
    representation of all (or only interactive) UI elements with names, types,
    bounding rectangles, and enabled states.

    Args:
        hwnd: Window handle to inspect.
        depth: Maximum tree depth to traverse (default 5).
        filter: "all" for all elements, "interactive" for only buttons,
                edits, combos, checkboxes, menu items, links, sliders, tabs.

    Returns:
        Structured result with element tree or error details.
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

    # Clamp depth
    if depth < 1:
        depth = 1
    elif depth > config.DEFAULT_UIA_DEPTH * 2:
        depth = config.DEFAULT_UIA_DEPTH * 2

    # Validate filter
    if filter not in ("all", "interactive"):
        return make_error(UIA_ERROR, f"Invalid filter '{filter}'. Must be 'all' or 'interactive'.")

    try:
        elements = get_ui_tree(hwnd, depth=depth, filter=filter)
        serialized = [elem.model_dump() for elem in elements]
        log_action("cv_read_ui", {"hwnd": hwnd, "depth": depth, "filter": filter}, "OK")
        return make_success(elements=serialized, count=len(serialized))
    except TimeoutError as exc:
        log_action("cv_read_ui", {"hwnd": hwnd}, "TIMEOUT")
        return make_error(UIA_ERROR, str(exc))
    except Exception as exc:
        log_action("cv_read_ui", {"hwnd": hwnd}, "ERROR")
        return make_error(UIA_ERROR, f"COM error reading UI tree: {exc}")
