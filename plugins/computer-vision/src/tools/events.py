"""MCP tool for polling UI events from the event buffer."""

from __future__ import annotations

import logging
from typing import Any

from src.server import mcp
from src.errors import make_error, make_success, INVALID_INPUT
from src.models import validate_hwnd
from src.utils.security import (
    check_restricted,
    log_action,
    get_process_name_by_pid,
    validate_hwnd_fresh,
)
from src.utils.events import get_event_manager

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_poll_events(hwnd: int | None = None) -> dict[str, Any]:
    """Poll and drain buffered UI events from the event manager.

    Read-only operation that returns all buffered events, optionally
    filtered to a specific window handle.

    Args:
        hwnd: Optional window handle to filter events for.
              If None, returns all buffered events.

    Returns:
        Dict with 'events' (list of event dicts) and 'count'.
    """
    try:
        # Validate hwnd if provided
        if hwnd is not None:
            try:
                validate_hwnd(hwnd)
            except ValueError as exc:
                return make_error(INVALID_INPUT, str(exc))

            # Check if window is still valid
            if not validate_hwnd_fresh(hwnd):
                return make_error(INVALID_INPUT, f"Window {hwnd} is no longer valid")

            # Security check: get process name and check restricted
            import ctypes
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                process_name = get_process_name_by_pid(pid.value)
                if process_name:
                    check_restricted(process_name)

        # Drain events
        manager = get_event_manager()
        events = manager.drain_events(hwnd=hwnd)

        # Convert to dicts
        event_dicts = [e.model_dump() for e in events]

        log_action("cv_poll_events", {"hwnd": hwnd}, "ok")

        return make_success(
            events=event_dicts,
            count=len(event_dicts),
        )

    except Exception as exc:
        return make_error(INVALID_INPUT, str(exc))
