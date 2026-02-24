"""MCP tools for screen capture: window, desktop, and region screenshots."""

from __future__ import annotations

import logging

from src.errors import (
    CAPTURE_FAILED,
    INVALID_COORDINATES,
    make_error,
    make_success,
    CVPluginError,
)
from src.coordinates import validate_coordinates
from src.server import mcp
from src.utils.screenshot import capture_desktop, capture_region, capture_window

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_screenshot_window(hwnd: int, max_width: int = 1280) -> dict:
    """Capture a screenshot of a specific window.

    Returns a file path to the saved PNG image plus window geometry and
    DPI metadata.  Use the Read tool on ``image_path`` to view the image.

    Args:
        hwnd: The window handle to capture.
        max_width: Maximum width in pixels for the output image. Default 1280.
    """
    try:
        result = capture_window(hwnd, max_width=max_width)
        return make_success(
            image_path=result.image_path,
            rect=result.rect.model_dump(),
            physical_resolution=result.physical_resolution,
            logical_resolution=result.logical_resolution,
            dpi_scale=result.dpi_scale,
            format=result.format,
        )
    except CVPluginError as exc:
        return exc.to_dict()
    except Exception as exc:
        logger.error("cv_screenshot_window failed: %s", exc)
        return make_error(CAPTURE_FAILED, f"Failed to capture window HWND {hwnd}: {exc}")


@mcp.tool()
def cv_screenshot_desktop(max_width: int = 1920) -> dict:
    """Capture a screenshot of the entire virtual desktop (all monitors).

    Returns a file path to the saved PNG image plus desktop geometry
    metadata.  Use the Read tool on ``image_path`` to view the image.

    Args:
        max_width: Maximum width in pixels for the output image. Default 1920.
    """
    try:
        result = capture_desktop(max_width=max_width)
        return make_success(
            image_path=result.image_path,
            rect=result.rect.model_dump(),
            physical_resolution=result.physical_resolution,
            logical_resolution=result.logical_resolution,
            dpi_scale=result.dpi_scale,
            format=result.format,
        )
    except CVPluginError as exc:
        return exc.to_dict()
    except Exception as exc:
        logger.error("cv_screenshot_desktop failed: %s", exc)
        return make_error(CAPTURE_FAILED, f"Failed to capture desktop: {exc}")


@mcp.tool()
def cv_screenshot_region(x0: int, y0: int, x1: int, y1: int, max_width: int = 1280) -> dict:
    """Capture a screenshot of a rectangular screen region.

    Coordinates are screen-absolute pixels. (x0,y0) is the top-left corner,
    (x1,y1) is the bottom-right corner.

    Args:
        x0: Left edge X coordinate.
        y0: Top edge Y coordinate.
        x1: Right edge X coordinate.
        y1: Bottom edge Y coordinate.
        max_width: Maximum width in pixels for the output image. Default 1280.
    """
    try:
        # Validate that corners are within the virtual desktop
        if not validate_coordinates(x0, y0):
            return make_error(
                INVALID_COORDINATES,
                f"Top-left corner ({x0}, {y0}) is outside the virtual desktop",
            )
        if not validate_coordinates(x1 - 1, y1 - 1):
            return make_error(
                INVALID_COORDINATES,
                f"Bottom-right corner ({x1}, {y1}) is outside the virtual desktop",
            )

        result = capture_region(x0, y0, x1, y1, max_width=max_width)
        return make_success(
            image_path=result.image_path,
            rect=result.rect.model_dump(),
            physical_resolution=result.physical_resolution,
            logical_resolution=result.logical_resolution,
            dpi_scale=result.dpi_scale,
            format=result.format,
        )
    except CVPluginError as exc:
        return exc.to_dict()
    except Exception as exc:
        logger.error("cv_screenshot_region failed: %s", exc)
        return make_error(CAPTURE_FAILED, f"Failed to capture region: {exc}")
