"""Unit tests for OcrEngine in src/utils/ocr_engine.py."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from src.models import OcrRegion, OcrWord, Rect, Point
from src.utils.ocr_engine import OcrEngine, _WINOCR_DEFAULT_CONFIDENCE


# ---------------------------------------------------------------------------
# Helpers for building mock winocr results
# ---------------------------------------------------------------------------

def _make_mock_bounding_rect(x: int, y: int, width: int, height: int):
    """Create a mock bounding_rect object with x, y, width, height attributes."""
    br = MagicMock()
    br.x = x
    br.y = y
    br.width = width
    br.height = height
    return br


def _make_mock_word(text: str, x: int, y: int, w: int, h: int):
    """Create a mock winocr word with text and bounding_rect."""
    word = MagicMock()
    word.text = text
    word.bounding_rect = _make_mock_bounding_rect(x, y, w, h)
    return word


def _make_mock_line(text: str, words: list):
    """Create a mock winocr line with text and words list."""
    line = MagicMock()
    line.text = text
    line.words = words
    return line


def _make_mock_winocr_result(lines: list):
    """Create a mock winocr recognition result."""
    result = MagicMock()
    result.lines = lines
    return result


def _create_mock_winocr(available_langs: list[str] | None = None):
    """Create a mock winocr module with list_available_languages."""
    mock = MagicMock()
    mock.list_available_languages.return_value = available_langs or ["en-US"]
    return mock


class TestLanguageDetection:
    """Tests for _detect_languages and _select_language."""

    def _fresh_engine(self) -> OcrEngine:
        """Create a fresh OcrEngine with no cached state."""
        engine = OcrEngine()
        engine._installed_langs = None
        return engine

    def test_caches_result(self):
        engine = self._fresh_engine()
        mock_winocr = _create_mock_winocr(["en-US", "es-MX"])
        with patch.dict(sys.modules, {"winocr": mock_winocr}):
            langs1 = engine._detect_languages()
            langs2 = engine._detect_languages()
            # Should only call once (cached)
            assert mock_winocr.list_available_languages.call_count == 1
            assert langs1 is langs2

    def test_preference_order_en_us_first(self):
        engine = self._fresh_engine()
        mock_winocr = _create_mock_winocr(["es-MX", "fr", "en-US", "de"])
        with patch.dict(sys.modules, {"winocr": mock_winocr}):
            langs = engine._detect_languages()
            assert langs[0] == "en-US"
            assert "es-MX" in langs
            assert "fr" in langs
            assert "de" in langs

    def test_preference_order_en_gb_when_no_en_us(self):
        engine = self._fresh_engine()
        mock_winocr = _create_mock_winocr(["es-MX", "en-GB", "ko"])
        with patch.dict(sys.modules, {"winocr": mock_winocr}):
            langs = engine._detect_languages()
            assert langs[0] == "en-GB"

    def test_empty_available_languages(self):
        engine = self._fresh_engine()
        # Directly set result to simulate winocr returning no languages
        # This tests the code path where available == []
        engine._installed_langs = []
        langs = engine._detect_languages()
        assert langs == []

    def test_winocr_unavailable_returns_empty(self):
        engine = self._fresh_engine()
        # Setting winocr to None in sys.modules makes `import winocr` raise ImportError
        with patch.dict(sys.modules, {"winocr": None}):
            langs = engine._detect_languages()
            assert langs == []

    def test_select_language_explicit(self):
        engine = OcrEngine()
        engine._installed_langs = ["en-US", "es-MX"]
        result = engine._select_language("fr")
        assert result == "fr"

    def test_select_language_auto_picks_first(self):
        engine = OcrEngine()
        engine._installed_langs = ["en-US", "es-MX"]
        result = engine._select_language(None)
        assert result == "en-US"

    def test_select_language_fallback_when_empty(self):
        engine = OcrEngine()
        engine._installed_langs = []
        result = engine._select_language(None)
        assert result == "en-US"  # default fallback


class TestPreprocessing:
    """Tests for preprocess_image pipeline."""

    def test_upscale_small_image(self):
        engine = OcrEngine()
        img = Image.new("RGB", (100, 50), color="white")
        result = engine.preprocess_image(img)
        assert result.width == 200
        assert result.height == 100

    def test_no_upscale_large_image(self):
        engine = OcrEngine()
        img = Image.new("RGB", (400, 400), color="white")
        result = engine.preprocess_image(img)
        assert result.width == 400
        assert result.height == 400

    def test_converts_to_grayscale(self):
        engine = OcrEngine()
        img = Image.new("RGB", (400, 400), color="red")
        result = engine.preprocess_image(img)
        assert result.mode == "L"

    def test_upscale_at_boundary(self):
        engine = OcrEngine()
        img = Image.new("RGB", (400, 300), color="white")
        result = engine.preprocess_image(img)
        assert result.height == 300

    def test_upscale_just_below_boundary(self):
        engine = OcrEngine()
        img = Image.new("RGB", (400, 299), color="white")
        result = engine.preprocess_image(img)
        assert result.height == 598

    def test_output_is_pil_image(self):
        engine = OcrEngine()
        img = Image.new("RGB", (400, 400), color="white")
        result = engine.preprocess_image(img)
        assert isinstance(result, Image.Image)


class TestWinocrBboxExtraction:
    """Tests for _extract_regions_winocr -- the core bug fix."""

    def test_basic_word_bboxes(self):
        engine = OcrEngine()
        word1 = _make_mock_word("Hello", 10, 20, 50, 15)
        word2 = _make_mock_word("World", 70, 20, 55, 15)
        line = _make_mock_line("Hello World", [word1, word2])

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions) == 1
        region = regions[0]
        assert region.text == "Hello World"
        assert region.bbox.x == 10
        assert region.bbox.y == 20
        assert region.bbox.width == 115  # (70 + 55) - 10
        assert region.bbox.height == 15
        assert len(region.words) == 2
        assert region.words[0].text == "Hello"
        assert region.words[0].bbox.x == 10
        assert region.words[1].text == "World"
        assert region.words[1].bbox.x == 70

    def test_origin_offset(self):
        engine = OcrEngine()
        word = _make_mock_word("Test", 10, 20, 40, 12)
        line = _make_mock_line("Test", [word])
        origin = Point(x=100, y=200)

        regions = engine._extract_regions_winocr([line], origin=origin)

        assert len(regions) == 1
        region = regions[0]
        assert region.bbox.x == 110
        assert region.bbox.y == 220
        assert region.words[0].bbox.x == 110
        assert region.words[0].bbox.y == 220

    def test_multiple_lines(self):
        engine = OcrEngine()
        line1 = _make_mock_line("Line one", [
            _make_mock_word("Line", 10, 10, 40, 15),
            _make_mock_word("one", 55, 10, 30, 15),
        ])
        line2 = _make_mock_line("Line two", [
            _make_mock_word("Line", 10, 30, 40, 15),
            _make_mock_word("two", 55, 30, 30, 15),
        ])

        regions = engine._extract_regions_winocr([line1, line2], origin=None)
        assert len(regions) == 2
        assert regions[0].text == "Line one"
        assert regions[1].text == "Line two"
        assert regions[0].bbox.y == 10
        assert regions[1].bbox.y == 30

    def test_word_confidence_default(self):
        engine = OcrEngine()
        word = _make_mock_word("Hi", 0, 0, 20, 10)
        line = _make_mock_line("Hi", [word])

        regions = engine._extract_regions_winocr([line], origin=None)
        assert regions[0].words[0].confidence == _WINOCR_DEFAULT_CONFIDENCE

    def test_empty_lines_list(self):
        engine = OcrEngine()
        regions = engine._extract_regions_winocr([], origin=None)
        assert regions == []

    def test_line_with_no_words(self):
        engine = OcrEngine()
        line = _make_mock_line("", [])
        regions = engine._extract_regions_winocr([line], origin=None)
        assert len(regions) == 1
        assert regions[0].text == ""
        assert regions[0].bbox.width == 0
        assert regions[0].bbox.height == 0
        assert regions[0].words == []


class TestPytesseractBboxExtraction:
    """Tests for _extract_regions_pytesseract."""

    def test_basic_extraction(self):
        engine = OcrEngine()
        data = {
            "text": ["Hello", "World", ""],
            "left": [10, 70, 0],
            "top": [20, 20, 0],
            "width": [50, 55, 0],
            "height": [15, 15, 0],
            "conf": [95, 88, -1],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        }

        regions = engine._extract_regions_pytesseract(data, origin=None)

        assert len(regions) == 1
        region = regions[0]
        assert region.text == "Hello World"
        assert len(region.words) == 2
        assert region.words[0].confidence == pytest.approx(0.95, abs=0.01)
        assert region.words[1].confidence == pytest.approx(0.88, abs=0.01)
        assert region.bbox.x == 10
        assert region.bbox.width == 115

    def test_origin_offset(self):
        engine = OcrEngine()
        data = {
            "text": ["Test"],
            "left": [10],
            "top": [20],
            "width": [40],
            "height": [12],
            "conf": [90],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }
        origin = Point(x=50, y=100)

        regions = engine._extract_regions_pytesseract(data, origin=origin)

        assert regions[0].bbox.x == 60
        assert regions[0].bbox.y == 120

    def test_negative_confidence_becomes_zero(self):
        engine = OcrEngine()
        data = {
            "text": ["word"],
            "left": [0],
            "top": [0],
            "width": [50],
            "height": [15],
            "conf": [-1],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }

        regions = engine._extract_regions_pytesseract(data, origin=None)
        assert regions[0].words[0].confidence == 0.0

    def test_empty_text_entries_skipped(self):
        engine = OcrEngine()
        data = {
            "text": ["", "  ", "Hello"],
            "left": [0, 0, 10],
            "top": [0, 0, 20],
            "width": [0, 0, 50],
            "height": [0, 0, 15],
            "conf": [0, 0, 95],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        }

        regions = engine._extract_regions_pytesseract(data, origin=None)
        assert len(regions) == 1
        assert len(regions[0].words) == 1
        assert regions[0].words[0].text == "Hello"

    def test_multiple_lines_grouped(self):
        engine = OcrEngine()
        data = {
            "text": ["Line", "one", "Line", "two"],
            "left": [10, 55, 10, 55],
            "top": [10, 10, 30, 30],
            "width": [40, 30, 40, 30],
            "height": [15, 15, 15, 15],
            "conf": [95, 90, 92, 88],
            "block_num": [1, 1, 1, 1],
            "par_num": [1, 1, 1, 1],
            "line_num": [1, 1, 2, 2],
        }

        regions = engine._extract_regions_pytesseract(data, origin=None)
        assert len(regions) == 2
        assert regions[0].text == "Line one"
        assert regions[1].text == "Line two"


class TestConfidenceAggregation:
    """Tests for _compute_confidence."""

    def test_single_region(self):
        engine = OcrEngine()
        regions = [OcrRegion(
            text="Hello",
            bbox=Rect(x=0, y=0, width=50, height=15),
            confidence=0.95,
            words=[OcrWord(text="Hello", bbox=Rect(x=0, y=0, width=50, height=15), confidence=0.95)],
        )]
        assert engine._compute_confidence(regions, "winocr") == pytest.approx(0.95)

    def test_multiple_words(self):
        engine = OcrEngine()
        regions = [OcrRegion(
            text="Hello World",
            bbox=Rect(x=0, y=0, width=100, height=15),
            confidence=0.9,
            words=[
                OcrWord(text="Hello", bbox=Rect(x=0, y=0, width=50, height=15), confidence=1.0),
                OcrWord(text="World", bbox=Rect(x=50, y=0, width=50, height=15), confidence=0.8),
            ],
        )]
        assert engine._compute_confidence(regions, "winocr") == pytest.approx(0.9)

    def test_empty_regions(self):
        engine = OcrEngine()
        assert engine._compute_confidence([], "winocr") == 0.0

    def test_region_without_words_uses_region_confidence(self):
        engine = OcrEngine()
        regions = [OcrRegion(
            text="Test",
            bbox=Rect(x=0, y=0, width=50, height=15),
            confidence=0.85,
            words=[],
        )]
        assert engine._compute_confidence(regions, "pytesseract") == pytest.approx(0.85)


class TestRecognizeIntegration:
    """Tests for the full recognize pipeline with mocked OCR backends."""

    def test_recognize_with_winocr(self):
        word = _make_mock_word("Hello", 10, 20, 50, 15)
        line = _make_mock_line("Hello", [word])
        mock_result = _make_mock_winocr_result([line])

        mock_winocr = _create_mock_winocr(["en-US"])

        async def mock_recognize_pil(img, lang="en-US"):
            return mock_result

        mock_winocr.recognize_pil = mock_recognize_pil

        with patch.dict(sys.modules, {"winocr": mock_winocr}):
            engine = OcrEngine()
            img = Image.new("RGB", (400, 400), color="white")
            result = engine.recognize(img, lang="en-US", preprocess=False)

            assert result["text"] == "Hello"
            assert result["engine"] == "winocr"
            assert result["language"] == "en-US"
            assert len(result["regions"]) == 1
            assert result["regions"][0].text == "Hello"
            assert result["regions"][0].bbox.x == 10
            assert result["confidence"] > 0

    def test_recognize_with_origin(self):
        word = _make_mock_word("Test", 5, 10, 30, 12)
        line = _make_mock_line("Test", [word])
        mock_result = _make_mock_winocr_result([line])

        mock_winocr = _create_mock_winocr(["en-US"])

        async def mock_recognize_pil(img, lang="en-US"):
            return mock_result

        mock_winocr.recognize_pil = mock_recognize_pil

        with patch.dict(sys.modules, {"winocr": mock_winocr}):
            engine = OcrEngine()
            img = Image.new("RGB", (400, 400), color="white")
            origin = Point(x=100, y=200)
            result = engine.recognize(img, lang="en-US", preprocess=False, origin=origin)

            assert result["origin"] == {"x": 100, "y": 200}
            region = result["regions"][0]
            assert region.bbox.x == 105
            assert region.bbox.y == 210
