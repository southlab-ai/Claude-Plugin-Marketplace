"""Screen capture utilities using mss with PrintWindow fallback."""

from __future__ import annotations

import ctypes
import logging
import os
import tempfile
import time
from typing import Any

import mss
import win32gui
import win32ui
import win32con
from PIL import Image

from src.dpi import get_window_dpi, get_scale_factor
from src.errors import WindowNotFoundError, CVPluginError, CAPTURE_FAILED
from src.models import Rect, ScreenshotResult
from src.utils.win32_window import is_window_valid

# Temp directory for saved screenshots — cleaned up automatically
_SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "cv_plugin_screenshots")
os.makedirs(_SCREENSHOT_DIR, exist_ok=True)

# Max age for screenshot files (seconds) before auto-cleanup
_MAX_AGE_SECONDS = 300

logger = logging.getLogger(__name__)


def _is_all_black(img: Image.Image) -> bool:
    """Check if an image is entirely black (all channels min==max==0)."""
    try:
        extrema = img.getextrema()
        # For RGB images, extrema is ((min_r, max_r), (min_g, max_g), (min_b, max_b))
        if isinstance(extrema[0], tuple):
            return all(mn == 0 and mx == 0 for mn, mx in extrema)
        # For single-channel images
        return extrema[0] == 0 and extrema[1] == 0
    except Exception:
        return False


def _capture_window_impl(hwnd: int) -> Image.Image:
    """Shared capture logic for window capture with PrintWindow-first 3-tier fallback.

    Handles minimized windows by temporarily showing them without activation.

    Tier 1: PrintWindow with PW_RENDERFULLCONTENT (flag=2) - validate not all-black
    Tier 2: PrintWindow with flag=0 - validate not all-black
    Tier 3: mss region capture as last resort

    Args:
        hwnd: Window handle to capture.

    Returns:
        PIL Image of the captured window.

    Raises:
        CVPluginError: If all capture methods fail.
    """
    # Handle minimized windows
    was_minimized = bool(ctypes.windll.user32.IsIconic(hwnd))
    if was_minimized:
        SW_SHOWNOACTIVATE = 4
        win32gui.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

    try:
        rect_tuple = win32gui.GetWindowRect(hwnd)
        left, top, right, bottom = rect_tuple
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            raise CVPluginError(CAPTURE_FAILED, f"Window HWND {hwnd} has zero size")

        # Tier 1: PrintWindow with PW_RENDERFULLCONTENT
        img = _capture_with_printwindow(hwnd, width, height, flag=2)
        if img is not None and not _is_all_black(img):
            return img

        # Tier 2: PrintWindow with flag=0
        img = _capture_with_printwindow(hwnd, width, height, flag=0)
        if img is not None and not _is_all_black(img):
            return img

        # Tier 3: mss region capture (last resort)
        img = _capture_region_mss(left, top, width, height)
        if img is not None:
            return img

        raise CVPluginError(CAPTURE_FAILED, f"Failed to capture window HWND {hwnd}")
    finally:
        if was_minimized:
            try:
                SW_MINIMIZE = 6
                win32gui.ShowWindow(hwnd, SW_MINIMIZE)
            except Exception:
                pass


def capture_window(hwnd: int, max_width: int = 1280) -> ScreenshotResult:
    """Capture a specific window by HWND.

    Uses PrintWindow-first 3-tier fallback for reliable capture of
    occluded or off-screen windows.

    Args:
        hwnd: Window handle to capture.
        max_width: Maximum width for downscaling. Default 1280.

    Returns:
        ScreenshotResult with base64-encoded image and metadata.
    """
    if not is_window_valid(hwnd):
        raise WindowNotFoundError(hwnd)

    img = _capture_window_impl(hwnd)

    rect_tuple = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect_tuple
    width = right - left
    height = bottom - top

    dpi = get_window_dpi(hwnd)
    scale = get_scale_factor(dpi)

    filepath = save_image(img, max_width=max_width)

    return ScreenshotResult(
        image_path=filepath,
        rect=Rect(x=left, y=top, width=width, height=height),
        physical_resolution={"width": img.width, "height": img.height},
        logical_resolution={
            "width": int(img.width / scale),
            "height": int(img.height / scale),
        },
        dpi_scale=scale,
        format="png",
    )


def capture_desktop(max_width: int = 1920) -> ScreenshotResult:
    """Capture the entire virtual desktop across all monitors.

    Args:
        max_width: Maximum width for downscaling. Default 1920.

    Returns:
        ScreenshotResult with base64-encoded image and metadata.
    """
    with mss.mss() as sct:
        # monitors[0] is the entire virtual desktop
        monitor = sct.monitors[0]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    filepath = save_image(img, max_width=max_width)

    return ScreenshotResult(
        image_path=filepath,
        rect=Rect(
            x=monitor["left"],
            y=monitor["top"],
            width=monitor["width"],
            height=monitor["height"],
        ),
        physical_resolution={"width": img.width, "height": img.height},
        logical_resolution={"width": img.width, "height": img.height},
        dpi_scale=1.0,
        format="png",
    )


def capture_region(x0: int, y0: int, x1: int, y1: int, max_width: int = 1280) -> ScreenshotResult:
    """Capture an arbitrary rectangular region of the screen.

    Args:
        x0: Left edge (screen-absolute).
        y0: Top edge (screen-absolute).
        x1: Right edge (screen-absolute).
        y1: Bottom edge (screen-absolute).
        max_width: Maximum width for downscaling.

    Returns:
        ScreenshotResult with base64-encoded image and metadata.
    """
    width = x1 - x0
    height = y1 - y0

    if width <= 0 or height <= 0:
        raise CVPluginError(
            CAPTURE_FAILED,
            f"Invalid region: ({x0},{y0})-({x1},{y1}) yields {width}x{height}",
        )

    region = {"left": x0, "top": y0, "width": width, "height": height}

    with mss.mss() as sct:
        screenshot = sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    filepath = save_image(img, max_width=max_width)

    return ScreenshotResult(
        image_path=filepath,
        rect=Rect(x=x0, y=y0, width=width, height=height),
        physical_resolution={"width": img.width, "height": img.height},
        logical_resolution={"width": img.width, "height": img.height},
        dpi_scale=1.0,
        format="png",
    )


def capture_window_raw(hwnd: int) -> Image.Image | None:
    """Capture a window and return as PIL Image (no encoding).

    Used internally by OCR to avoid decode-encode round-trips.
    Returns None on failure.
    """
    if not is_window_valid(hwnd):
        return None

    try:
        return _capture_window_impl(hwnd)
    except Exception as exc:
        logger.debug("capture_window_raw failed for HWND %s: %s", hwnd, exc)
        return None


def capture_region_raw(x0: int, y0: int, x1: int, y1: int) -> Image.Image | None:
    """Capture a screen region and return as PIL Image (no encoding).

    Used internally by OCR to avoid encode-decode round-trips.
    Returns None on failure.
    """
    width = x1 - x0
    height = y1 - y0
    if width <= 0 or height <= 0:
        return None
    try:
        return _capture_region_mss(x0, y0, width, height)
    except Exception as exc:
        logger.debug("capture_region_raw failed for (%s,%s)-(%s,%s): %s", x0, y0, x1, y1, exc)
        return None


def _capture_region_mss(left: int, top: int, width: int, height: int) -> Image.Image | None:
    """Capture a screen region using mss. Returns PIL Image or None on failure."""
    try:
        region = {"left": left, "top": top, "width": width, "height": height}
        with mss.mss() as sct:
            screenshot = sct.grab(region)
            return Image.frombytes("RGB", screenshot.size, screenshot.rgb)
    except Exception as exc:
        logger.debug("mss capture failed for region (%s,%s,%s,%s): %s", left, top, width, height, exc)
        return None


def _capture_with_printwindow(hwnd: int, width: int, height: int, flag: int = 2) -> Image.Image | None:
    """Capture a window using PrintWindow (works for occluded windows).

    Args:
        hwnd: Window handle.
        width: Capture width in pixels.
        height: Capture height in pixels.
        flag: PrintWindow flag. 2 = PW_RENDERFULLCONTENT, 0 = default.

    Returns PIL Image or None on failure.
    """
    hdc_window = None
    hdc_mem = None
    hdc_compat = None
    bitmap = None
    try:
        hdc_window = win32gui.GetWindowDC(hwnd)
        hdc_mem = win32ui.CreateDCFromHandle(hdc_window)
        hdc_compat = hdc_mem.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(hdc_mem, width, height)
        hdc_compat.SelectObject(bitmap)

        result = ctypes.windll.user32.PrintWindow(hwnd, hdc_compat.GetSafeHdc(), flag)

        if not result:
            return None

        bmp_info = bitmap.GetInfo()
        bmp_bits = bitmap.GetBitmapBits(True)

        img = Image.frombuffer(
            "RGB",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_bits,
            "raw",
            "BGRX",
            0,
            1,
        )
        return img
    except Exception as exc:
        logger.debug("PrintWindow(flag=%d) failed for HWND %s: %s", flag, hwnd, exc)
        return None
    finally:
        if bitmap is not None:
            try:
                win32gui.DeleteObject(bitmap.GetHandle())
            except Exception:
                pass
        if hdc_compat is not None:
            try:
                hdc_compat.DeleteDC()
            except Exception:
                pass
        if hdc_mem is not None:
            try:
                hdc_mem.DeleteDC()
            except Exception:
                pass
        if hdc_window is not None:
            try:
                win32gui.ReleaseDC(hwnd, hdc_window)
            except Exception:
                pass


def _cleanup_old_screenshots() -> None:
    """Remove screenshot files older than _MAX_AGE_SECONDS."""
    try:
        now = time.time()
        for fname in os.listdir(_SCREENSHOT_DIR):
            fpath = os.path.join(_SCREENSHOT_DIR, fname)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > _MAX_AGE_SECONDS:
                os.remove(fpath)
    except Exception:
        pass  # best-effort cleanup


_cleanup_call_count: int = 0


def save_image(img: Image.Image, max_width: int = 1280, fmt: str = "png") -> str:
    """Downscale and save a PIL Image to a temp file.

    Args:
        img: PIL Image to save.
        max_width: Maximum width for downscaling.
        fmt: Image format ("png" or "jpeg").

    Returns:
        Absolute file path to the saved image.
    """
    global _cleanup_call_count
    _cleanup_call_count += 1
    if _cleanup_call_count % 10 == 0:
        _cleanup_old_screenshots()

    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

    timestamp = int(time.time() * 1000)
    filename = f"cv_{timestamp}.{fmt}"
    filepath = os.path.join(_SCREENSHOT_DIR, filename)

    if fmt.lower() == "jpeg":
        img = img.convert("RGB")
        img.save(filepath, format="JPEG", quality=95)
    else:
        img.save(filepath, format="PNG")

    return filepath
