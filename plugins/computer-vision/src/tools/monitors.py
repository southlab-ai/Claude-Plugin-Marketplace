"""MCP tool for listing display monitors."""

from __future__ import annotations

import logging

import win32api

from src.dpi import get_monitor_dpi, get_scale_factor
from src.errors import make_error, make_success
from src.models import MonitorInfo, Rect
from src.server import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_list_monitors() -> dict:
    """List all display monitors with resolution, DPI, and work-area information.

    Returns monitor index, name, resolution, work area, DPI, scale factor,
    and whether it is the primary monitor.
    """
    try:
        monitors_raw = win32api.EnumDisplayMonitors(None, None)
        monitors: list[dict] = []

        for i, (hmonitor, _hdc, _rect) in enumerate(monitors_raw):
            try:
                info = win32api.GetMonitorInfo(hmonitor)
                # info["Monitor"] = (left, top, right, bottom)
                # info["Work"] = (left, top, right, bottom)
                # info["Device"] = device name string
                # info["Flags"] = 1 if primary

                mon_rect = info["Monitor"]
                work_rect = info["Work"]
                device_name = info.get("Device", f"Monitor-{i}")
                is_primary = bool(info.get("Flags", 0) & 1)

                dpi_x, _dpi_y = get_monitor_dpi(int(hmonitor))
                scale = get_scale_factor(dpi_x)

                monitor_info = MonitorInfo(
                    index=i,
                    name=device_name,
                    rect=Rect(
                        x=mon_rect[0],
                        y=mon_rect[1],
                        width=mon_rect[2] - mon_rect[0],
                        height=mon_rect[3] - mon_rect[1],
                    ),
                    work_area=Rect(
                        x=work_rect[0],
                        y=work_rect[1],
                        width=work_rect[2] - work_rect[0],
                        height=work_rect[3] - work_rect[1],
                    ),
                    dpi=dpi_x,
                    scale_factor=scale,
                    is_primary=is_primary,
                )
                monitors.append(monitor_info.model_dump())
            except Exception as exc:
                logger.warning("Failed to get info for monitor %d: %s", i, exc)
                continue

        return make_success(monitors=monitors, count=len(monitors))

    except Exception as exc:
        logger.error("cv_list_monitors failed: %s", exc)
        return make_error("CAPTURE_FAILED", f"Failed to enumerate monitors: {exc}")
