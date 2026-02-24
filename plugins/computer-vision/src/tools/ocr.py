"""MCP tool for OCR text extraction using OcrEngine (winocr primary, pytesseract fallback)."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from PIL import Image

from src.server import mcp
from src.errors import (
    make_error, make_success,
    OCR_UNAVAILABLE, INVALID_INPUT, CAPTURE_FAILED, WINDOW_NOT_FOUND,
)
from src.utils.security import redact_ocr_output
from src.utils.screenshot import capture_window_raw, capture_region_raw
from src.utils.ocr_engine import get_engine
from src.models import Point

logger = logging.getLogger(__name__)


@mcp.tool()
def cv_ocr(
    hwnd: int | None = None,
    x0: int | None = None,
    y0: int | None = None,
    x1: int | None = None,
    y1: int | None = None,
    image_base64: str | None = None,
    lang: str | None = None,
    preprocess: bool = True,
) -> dict:
    """Extract text from a screenshot using OCR.

    Provide one of:
    - image_base64: a base64-encoded image to OCR directly.
    - hwnd: a window handle to capture and OCR.
    - x0, y0, x1, y1: a screen region to capture and OCR.
    If none provided, returns an error.

    Args:
        hwnd: Window handle to capture and OCR.
        x0: Left edge of region to capture.
        y0: Top edge of region to capture.
        x1: Right edge of region to capture.
        y1: Bottom edge of region to capture.
        image_base64: Base64-encoded image to OCR directly.
        lang: OCR language tag (e.g. "en-US"). Auto-detected if not provided.
        preprocess: Whether to apply image preprocessing for better accuracy.
    """
    try:
        # Security gates for hwnd
        if hwnd is not None:
            from src.utils.security import (
                validate_hwnd_fresh, validate_hwnd_range,
                check_restricted, get_process_name_by_pid, log_action,
            )
            validate_hwnd_range(hwnd)
            if not validate_hwnd_fresh(hwnd):
                return make_error(WINDOW_NOT_FOUND, f"Window HWND={hwnd} no longer exists")
            import win32gui
            import win32process
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = get_process_name_by_pid(pid)
            check_restricted(process_name)
            log_action("cv_ocr", {"hwnd": hwnd, "lang": lang, "preprocess": preprocess}, "started")

        image: Image.Image | None = None
        origin: Point | None = None

        # Resolve image source
        if image_base64:
            try:
                raw = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(raw))
            except Exception as e:
                return make_error(INVALID_INPUT, f"Failed to decode base64 image: {e}")

        elif hwnd is not None:
            import win32gui as _w32g
            rect_tuple = _w32g.GetWindowRect(hwnd)
            origin = Point(x=rect_tuple[0], y=rect_tuple[1])
            image = capture_window_raw(hwnd)
            if image is None:
                return make_error(CAPTURE_FAILED, f"Failed to capture window HWND={hwnd}")

        elif all(v is not None for v in (x0, y0, x1, y1)):
            origin = Point(x=x0, y=y0)
            image = capture_region_raw(x0, y0, x1, y1)
            if image is None:
                return make_error(CAPTURE_FAILED, f"Failed to capture region ({x0},{y0})-({x1},{y1})")
        else:
            return make_error(
                INVALID_INPUT,
                "Provide one of: image_base64, hwnd, or (x0, y0, x1, y1) region coordinates.",
            )

        # Run OCR via OcrEngine
        engine = get_engine()
        try:
            result = engine.recognize(image, lang=lang, preprocess=preprocess, origin=origin)
        except RuntimeError as e:
            return make_error(OCR_UNAVAILABLE, str(e))

        full_text: str = result["text"]
        regions = result["regions"]
        engine_name: str = result["engine"]
        confidence: float = result["confidence"]
        language: str = result["language"]
        origin_dict = result["origin"]

        # Serialize regions to dicts for redaction
        region_dicts = [r.model_dump() for r in regions]

        # Apply redaction
        full_text, region_dicts = redact_ocr_output(full_text, region_dicts)

        # Log completion for hwnd
        if hwnd is not None:
            from src.utils.security import log_action
            log_action("cv_ocr", {"hwnd": hwnd, "lang": lang, "preprocess": preprocess}, "completed")

        return make_success(
            text=full_text,
            regions=region_dicts,
            engine=engine_name,
            confidence=confidence,
            language=language,
            origin=origin_dict,
        )

    except Exception as e:
        return make_error(OCR_UNAVAILABLE, str(e))
