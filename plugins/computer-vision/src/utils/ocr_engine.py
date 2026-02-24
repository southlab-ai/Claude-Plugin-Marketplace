"""OcrEngine: centralised OCR pipeline with preprocessing, language detection, and bbox extraction."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from src.models import OcrRegion, OcrWord, Rect, Point

logger = logging.getLogger(__name__)

# Default confidence for winocr (it does not expose per-word confidence)
_WINOCR_DEFAULT_CONFIDENCE = 0.95

# Minimum image height before upscaling is applied
_MIN_HEIGHT_FOR_UPSCALE = 300

# Language preference order for auto-detection
_LANG_PREFERENCE = [
    "en-US", "en-GB", "en-AU", "en-CA", "en-IN",  # English variants
    "es", "es-MX", "es-ES",
    "pt", "pt-BR",
    "fr", "de", "it", "ja", "zh-Hans", "ko",
]


class OcrEngine:
    """Centralised OCR engine with winocr primary and pytesseract fallback."""

    def __init__(self) -> None:
        self._installed_langs: list[str] | None = None  # lazy cached

    def recognize(
        self,
        image: Image.Image,
        lang: str | None = None,
        preprocess: bool = True,
        origin: Point | None = None,
    ) -> dict[str, Any]:
        """Main OCR pipeline.

        Args:
            image: PIL Image to OCR.
            lang: Explicit language tag (e.g. "en-US"). Auto-detected if None.
            preprocess: Whether to apply preprocessing pipeline.
            origin: Screen-absolute origin for translating bbox coordinates.

        Returns:
            dict with keys: text, regions, engine, confidence, language, origin.
        """
        if preprocess:
            image = self.preprocess_image(image)

        # Try winocr first, then pytesseract fallback
        engine = "winocr"
        selected_lang = ""
        regions: list[OcrRegion] = []
        full_text = ""

        try:
            selected_lang = self._select_language(lang)
            full_text, regions = self._run_winocr(image, selected_lang, origin)
        except ImportError:
            logger.info("winocr not available, trying pytesseract fallback")
            engine = "pytesseract"
            try:
                full_text, regions = self._run_pytesseract(image, origin)
                selected_lang = "eng"
            except ImportError:
                raise RuntimeError(
                    "No OCR engine available. Install winocr (pip install winocr) or pytesseract."
                )
        except Exception as e:
            logger.warning("winocr failed (%s), trying pytesseract fallback", e)
            engine = "pytesseract"
            try:
                full_text, regions = self._run_pytesseract(image, origin)
                selected_lang = "eng"
            except ImportError:
                raise RuntimeError(
                    f"winocr failed ({e}) and pytesseract is not installed."
                )
            except Exception as e2:
                raise RuntimeError(f"Both OCR engines failed: winocr={e}, pytesseract={e2}")

        # Compute overall confidence
        confidence = self._compute_confidence(regions, engine)

        return {
            "text": full_text,
            "regions": regions,
            "engine": engine,
            "confidence": confidence,
            "language": selected_lang,
            "origin": origin.model_dump() if origin else None,
        }

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocessing pipeline to improve OCR accuracy.

        Steps:
        1. Upscale 2x with LANCZOS if height < 300px
        2. Convert to grayscale ("L")
        3. Apply SHARPEN filter
        4. Apply autocontrast
        """
        # 1. Upscale small images
        if image.height < _MIN_HEIGHT_FOR_UPSCALE:
            new_width = image.width * 2
            new_height = image.height * 2
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 2. Grayscale
        image = image.convert("L")

        # 3. Sharpen
        image = image.filter(ImageFilter.SHARPEN)

        # 4. Autocontrast
        image = ImageOps.autocontrast(image)

        return image

    def _detect_languages(self) -> list[str]:
        """Detect installed OCR languages via winocr. Cache the result.

        Preference: en-US > en-* > other installed languages.
        """
        if self._installed_langs is not None:
            return self._installed_langs

        try:
            import winocr
            available = winocr.list_available_languages()
        except Exception:
            self._installed_langs = []
            return self._installed_langs

        if not available:
            self._installed_langs = []
            return self._installed_langs

        # Sort by preference: exact matches in _LANG_PREFERENCE first, then the rest
        available_set = set(available)
        ordered: list[str] = []

        for pref in _LANG_PREFERENCE:
            if pref in available_set:
                ordered.append(pref)
                available_set.discard(pref)

        # Add remaining languages not in preference list
        ordered.extend(sorted(available_set))

        self._installed_langs = ordered
        logger.info("Detected OCR languages: %s", ordered)
        return self._installed_langs

    def _select_language(self, lang: str | None) -> str:
        """Select the OCR language to use.

        If lang is provided, validate it against installed languages.
        If None, use the first language from the preference-ordered list.
        """
        installed = self._detect_languages()

        if lang is not None:
            # Validate explicit language
            if installed and lang not in installed:
                logger.warning(
                    "Requested language '%s' not in installed list %s; attempting anyway",
                    lang, installed,
                )
            return lang

        if not installed:
            # Fallback: let winocr try common languages
            return "en-US"

        return installed[0]

    def _run_winocr(
        self, image: Image.Image, lang: str, origin: Point | None
    ) -> tuple[str, list[OcrRegion]]:
        """Run winocr and extract structured results."""
        import winocr

        async def _recognize(img: Image.Image, language: str):
            return await winocr.recognize_pil(img, lang=language)

        def _sync_run(img: Image.Image, language: str):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, _recognize(img, language)).result()
            else:
                return asyncio.run(_recognize(img, language))

        result = _sync_run(image, lang)
        lines = result.lines if hasattr(result, "lines") else []

        full_text_parts: list[str] = []
        regions = self._extract_regions_winocr(lines, origin)

        for region in regions:
            full_text_parts.append(region.text)

        full_text = "\n".join(full_text_parts)
        return full_text, regions

    def _extract_regions_winocr(
        self, lines: list[Any], origin: Point | None
    ) -> list[OcrRegion]:
        """Extract OcrRegion objects from winocr result lines.

        THE KEY BUG FIX: winocr exposes bounding boxes via line.words[i].bounding_rect,
        NOT via line.x or line.bbox. We iterate words, extract bounding_rect, and compute
        line-level bbox as the union of all word bboxes.
        """
        ox = origin.x if origin else 0
        oy = origin.y if origin else 0
        regions: list[OcrRegion] = []

        for line in lines:
            line_text = line.text if hasattr(line, "text") else str(line)
            words_attr = line.words if hasattr(line, "words") else []

            ocr_words: list[OcrWord] = []
            min_x: int | None = None
            min_y: int | None = None
            max_x2: int | None = None
            max_y2: int | None = None

            for word in words_attr:
                word_text = word.text if hasattr(word, "text") else str(word)
                br = word.bounding_rect if hasattr(word, "bounding_rect") else None

                if br is not None:
                    wx = int(br.x) + ox
                    wy = int(br.y) + oy
                    ww = int(br.width)
                    wh = int(br.height)
                else:
                    wx, wy, ww, wh = 0, 0, 0, 0

                word_rect = Rect(x=wx, y=wy, width=ww, height=wh)
                ocr_words.append(OcrWord(
                    text=word_text,
                    bbox=word_rect,
                    confidence=_WINOCR_DEFAULT_CONFIDENCE,
                ))

                # Update line-level bounding box (union of word bboxes)
                if ww > 0 and wh > 0:
                    x2 = wx + ww
                    y2 = wy + wh
                    if min_x is None:
                        min_x, min_y, max_x2, max_y2 = wx, wy, x2, y2
                    else:
                        min_x = min(min_x, wx)
                        min_y = min(min_y, wy)
                        max_x2 = max(max_x2, x2)
                        max_y2 = max(max_y2, y2)

            # Build line-level bbox from union of word bboxes
            if min_x is not None:
                line_rect = Rect(
                    x=min_x, y=min_y,
                    width=max_x2 - min_x, height=max_y2 - min_y,
                )
            else:
                line_rect = Rect(x=ox, y=oy, width=0, height=0)

            line_confidence = (
                sum(w.confidence for w in ocr_words) / len(ocr_words)
                if ocr_words else _WINOCR_DEFAULT_CONFIDENCE
            )

            regions.append(OcrRegion(
                text=line_text,
                bbox=line_rect,
                confidence=line_confidence,
                words=ocr_words,
            ))

        return regions

    def _run_pytesseract(
        self, image: Image.Image, origin: Point | None
    ) -> tuple[str, list[OcrRegion]]:
        """Run pytesseract and extract structured results."""
        import pytesseract

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        regions = self._extract_regions_pytesseract(data, origin)

        full_text_parts: list[str] = []
        for region in regions:
            full_text_parts.append(region.text)

        full_text = " ".join(full_text_parts)
        return full_text, regions

    def _extract_regions_pytesseract(
        self, data: dict[str, Any], origin: Point | None
    ) -> list[OcrRegion]:
        """Extract OcrRegion objects from pytesseract image_to_data output.

        Groups words by line number and builds line-level regions.
        """
        ox = origin.x if origin else 0
        oy = origin.y if origin else 0

        n_boxes = len(data.get("text", []))

        # Group words by (block_num, par_num, line_num)
        lines_dict: dict[tuple[int, int, int], list[int]] = {}
        for i in range(n_boxes):
            text = data["text"][i].strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            if key not in lines_dict:
                lines_dict[key] = []
            lines_dict[key].append(i)

        regions: list[OcrRegion] = []
        for _key, indices in sorted(lines_dict.items()):
            words: list[OcrWord] = []
            line_texts: list[str] = []
            min_x: int | None = None
            min_y: int | None = None
            max_x2: int | None = None
            max_y2: int | None = None

            for idx in indices:
                word_text = data["text"][idx].strip()
                if not word_text:
                    continue

                wx = int(data["left"][idx]) + ox
                wy = int(data["top"][idx]) + oy
                ww = int(data["width"][idx])
                wh = int(data["height"][idx])
                conf = float(data["conf"][idx])
                # pytesseract returns -1 for invalid conf
                if conf < 0:
                    conf = 0.0
                else:
                    conf = conf / 100.0  # normalize to 0-1

                word_rect = Rect(x=wx, y=wy, width=ww, height=wh)
                words.append(OcrWord(text=word_text, bbox=word_rect, confidence=conf))
                line_texts.append(word_text)

                x2 = wx + ww
                y2 = wy + wh
                if min_x is None:
                    min_x, min_y, max_x2, max_y2 = wx, wy, x2, y2
                else:
                    min_x = min(min_x, wx)
                    min_y = min(min_y, wy)
                    max_x2 = max(max_x2, x2)
                    max_y2 = max(max_y2, y2)

            if not words:
                continue

            line_rect = Rect(
                x=min_x, y=min_y,
                width=max_x2 - min_x, height=max_y2 - min_y,
            )
            line_text = " ".join(line_texts)
            line_confidence = sum(w.confidence for w in words) / len(words)

            regions.append(OcrRegion(
                text=line_text,
                bbox=line_rect,
                confidence=line_confidence,
                words=words,
            ))

        return regions

    def _compute_confidence(self, regions: list[OcrRegion], engine: str) -> float:
        """Compute overall confidence as the weighted average across all regions."""
        if not regions:
            return 0.0

        total_words = 0
        weighted_sum = 0.0
        for region in regions:
            if region.words:
                for word in region.words:
                    weighted_sum += word.confidence
                    total_words += 1
            else:
                weighted_sum += region.confidence
                total_words += 1

        return weighted_sum / total_words if total_words > 0 else 0.0


# Module-level singleton with lazy init
_engine: OcrEngine | None = None


def get_engine() -> OcrEngine:
    """Get the module-level OcrEngine singleton."""
    global _engine
    if _engine is None:
        _engine = OcrEngine()
    return _engine
