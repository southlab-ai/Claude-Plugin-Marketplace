"""Scene analysis — OpenCV element detection with OCR labeling."""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image, ImageDraw

from src.models import Point

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np

    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Intersection over Union for (x, y, w, h) boxes."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: list[tuple[int, int, int, int]], threshold: float = 0.3) -> list[int]:
    """Non-maximum suppression. Returns indices to keep (largest-area first)."""
    if not boxes:
        return []
    indices = sorted(range(len(boxes)), key=lambda i: boxes[i][2] * boxes[i][3], reverse=True)
    keep: list[int] = []
    while indices:
        i = indices.pop(0)
        keep.append(i)
        indices = [j for j in indices if _iou(boxes[i], boxes[j]) < threshold]
    return keep


def _is_rectangular(contour, tolerance: float = 0.04) -> bool:
    """Check if a contour is roughly rectangular."""
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, tolerance * peri, True)
    return 4 <= len(approx) <= 8


def _valid_box(x: int, y: int, w: int, h: int, min_area: int, max_area: int) -> bool:
    """Check if a bounding box meets size, dimension, and aspect ratio criteria."""
    area = w * h
    if area < min_area or area > max_area:
        return False
    if min(w, h) < 25:
        return False
    aspect = max(w, h) / max(min(w, h), 1)
    return aspect < 6


def detect_elements(
    img: Image.Image,
    min_area: int = 800,
    max_area_ratio: float = 0.35,
) -> list[dict[str, Any]]:
    """Detect rectangular elements using multi-strategy OpenCV detection.

    Strategies:
    1. Canny edge detection — finds bordered elements
    2. Multi-level binary threshold — isolates objects at different contrasts
       (high threshold catches white cards on colored backgrounds)
    3. HSV saturation filter — finds desaturated (white/gray) regions on
       saturated backgrounds (cards on green felt)

    Returns list of dicts with id, label, bbox {x, y, width, height},
    center {x, y} — all in image pixel coordinates.
    """
    if not _HAS_CV2:
        raise ImportError(
            "opencv-python-headless is required for cv_scene. "
            "Install with: uv add opencv-python-headless"
        )

    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    img_area = img.width * img.height
    max_area = int(img_area * max_area_ratio)

    all_boxes: list[tuple[int, int, int, int]] = []
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Strategy 1: Canny edge detection
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    for c in contours:
        if _is_rectangular(c, 0.02):
            x, y, w, h = cv2.boundingRect(c)
            if _valid_box(x, y, w, h, min_area, max_area):
                all_boxes.append((x, y, w, h))

    # Strategy 2: Multi-level binary threshold
    for thresh_val in [140, 190, 230]:
        _, binary = cv2.threshold(blurred, thresh_val, 255, cv2.THRESH_BINARY)
        contours2, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours2:
            if _is_rectangular(c, 0.03):
                x, y, w, h = cv2.boundingRect(c)
                if _valid_box(x, y, w, h, min_area, max_area):
                    all_boxes.append((x, y, w, h))

    # Strategy 3: HSV saturation filter (white/gray objects on colored background)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    # Low saturation + high value = white/light gray
    low_sat_mask = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
    # Clean up with morphological close
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    low_sat_mask = cv2.morphologyEx(low_sat_mask, cv2.MORPH_CLOSE, close_kernel)
    contours3, _ = cv2.findContours(low_sat_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for c in contours3:
        x, y, w, h = cv2.boundingRect(c)
        if _valid_box(x, y, w, h, min_area, max_area):
            all_boxes.append((x, y, w, h))

    # Non-maximum suppression + row-major sort
    kept = [all_boxes[i] for i in _nms(all_boxes, 0.3)]
    kept.sort(key=lambda b: (b[1] // 50, b[0]))

    return [
        {
            "id": idx,
            "label": "",
            "bbox": {"x": x, "y": y, "width": w, "height": h},
            "center": {"x": x + w // 2, "y": y + h // 2},
        }
        for idx, (x, y, w, h) in enumerate(kept, 1)
    ]


def label_with_ocr(elements: list[dict[str, Any]], img: Image.Image) -> None:
    """Label elements using OCR text that falls within their bounding boxes (in-place)."""
    try:
        from src.utils.ocr_engine import get_engine
        engine = get_engine()
    except Exception:
        return

    try:
        result = engine.recognize(img, preprocess=True, origin=Point(x=0, y=0))
    except Exception as exc:
        logger.debug("OCR for scene labeling failed: %s", exc)
        return

    regions = result.get("regions", [])
    if not regions:
        return

    # Collect all word centers
    words: list[tuple[str, int, int]] = []
    for region in regions:
        if hasattr(region, "words") and region.words:
            for w in region.words:
                words.append((w.text, w.bbox.x + w.bbox.width // 2, w.bbox.y + w.bbox.height // 2))
        elif hasattr(region, "text") and region.text:
            words.append((region.text, region.bbox.x + region.bbox.width // 2, region.bbox.y + region.bbox.height // 2))

    # Match words to elements by containment
    for el in elements:
        b = el["bbox"]
        x1, y1 = b["x"], b["y"]
        x2, y2 = x1 + b["width"], y1 + b["height"]
        matched = [text for text, wx, wy in words if x1 <= wx <= x2 and y1 <= wy <= y2]
        if matched:
            el["label"] = " ".join(matched)


def add_screen_coordinates(
    elements: list[dict[str, Any]],
    window_x: int,
    window_y: int,
) -> None:
    """Add screen-absolute center coordinates to each element (in-place)."""
    for el in elements:
        c = el["center"]
        el["center_screen"] = {"x": window_x + c["x"], "y": window_y + c["y"]}


def annotate_image(
    img: Image.Image,
    elements: list[dict[str, Any]],
    src_width: int | None = None,
    src_height: int | None = None,
) -> Image.Image:
    """Draw numbered bounding boxes on the (possibly downscaled) image.

    Args:
        img: Display image (possibly downscaled).
        elements: Elements with bbox in original image coordinates.
        src_width/src_height: Original image dimensions for coordinate mapping.
    """
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    sx = (src_width / base.width) if src_width and base.width else 1.0
    sy = (src_height / base.height) if src_height and base.height else 1.0

    for el in elements:
        b = el["bbox"]
        x = int(b["x"] / sx)
        y = int(b["y"] / sy)
        w = int(b["width"] / sx)
        h = int(b["height"] / sy)

        # Bounding box — cyan with good visibility
        draw.rectangle([(x, y), (x + w, y + h)], outline=(0, 220, 255, 220), width=2)

        # Label with background
        label = f"#{el['id']}"
        if el.get("label"):
            lbl = el["label"][:20]
            label += f" {lbl}"
        tw = len(label) * 7 + 6
        th = 16
        ly = max(y - th - 1, 0)

        draw.rectangle([(x, ly), (x + tw, ly + th)], fill=(0, 100, 200, 230))
        draw.text((x + 3, ly + 1), label, fill=(255, 255, 255, 255))

    return Image.alpha_composite(base, overlay).convert("RGB")
