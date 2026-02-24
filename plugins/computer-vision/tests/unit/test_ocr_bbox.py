"""Regression tests for the OCR bounding box fix.

Verifies that winocr word.bounding_rect is correctly extracted and that
every region has a non-empty bbox when words have valid bounding rects.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import OcrRegion, OcrWord, Rect, Point
from src.utils.ocr_engine import OcrEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bounding_rect(x: int, y: int, width: int, height: int):
    br = MagicMock()
    br.x = x
    br.y = y
    br.width = width
    br.height = height
    return br


def _make_word(text: str, x: int, y: int, w: int, h: int):
    word = MagicMock()
    word.text = text
    word.bounding_rect = _make_bounding_rect(x, y, w, h)
    return word


def _make_line(text: str, words: list):
    line = MagicMock()
    line.text = text
    line.words = words
    return line


# ---------------------------------------------------------------------------
# Regression: every region with real words MUST have a non-empty bbox
# ---------------------------------------------------------------------------

class TestBboxNonEmpty:
    """Verify the core fix: bboxes are never empty when words have bounding rects."""

    def test_single_word_line_has_bbox(self):
        engine = OcrEngine()
        word = _make_word("Hello", 10, 20, 50, 15)
        line = _make_line("Hello", [word])

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions) == 1
        bbox = regions[0].bbox
        assert bbox.width > 0
        assert bbox.height > 0
        assert bbox.x == 10
        assert bbox.y == 20
        assert bbox.width == 50
        assert bbox.height == 15

    def test_multi_word_line_has_bbox(self):
        engine = OcrEngine()
        words = [
            _make_word("The", 5, 10, 30, 14),
            _make_word("quick", 40, 10, 45, 14),
            _make_word("brown", 90, 10, 50, 14),
            _make_word("fox", 145, 10, 30, 14),
        ]
        line = _make_line("The quick brown fox", words)

        regions = engine._extract_regions_winocr([line], origin=None)

        bbox = regions[0].bbox
        # Union: x=5, y=10, width=(145+30)-5=170, height=14
        assert bbox.x == 5
        assert bbox.y == 10
        assert bbox.width == 170
        assert bbox.height == 14

    def test_all_regions_have_nonempty_bbox(self):
        """Multiple lines should all have non-empty bboxes."""
        engine = OcrEngine()
        lines = [
            _make_line("First line", [
                _make_word("First", 10, 10, 45, 15),
                _make_word("line", 60, 10, 35, 15),
            ]),
            _make_line("Second line", [
                _make_word("Second", 10, 30, 55, 15),
                _make_word("line", 70, 30, 35, 15),
            ]),
            _make_line("Third line", [
                _make_word("Third", 10, 50, 45, 15),
                _make_word("line", 60, 50, 35, 15),
            ]),
        ]

        regions = engine._extract_regions_winocr(lines, origin=None)

        assert len(regions) == 3
        for region in regions:
            assert region.bbox.width > 0, f"Region '{region.text}' has zero width"
            assert region.bbox.height > 0, f"Region '{region.text}' has zero height"

    def test_words_list_populated(self):
        """Verify that each region has its words list populated with OcrWord objects."""
        engine = OcrEngine()
        words = [
            _make_word("Hello", 10, 20, 50, 15),
            _make_word("World", 70, 20, 55, 15),
        ]
        line = _make_line("Hello World", words)

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions[0].words) == 2
        for w in regions[0].words:
            assert isinstance(w, OcrWord)
            assert w.bbox.width > 0
            assert w.bbox.height > 0


class TestEmptyLineEdgeCases:
    """Edge cases with empty or unusual lines."""

    def test_empty_line_no_words(self):
        engine = OcrEngine()
        line = _make_line("", [])

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions) == 1
        assert regions[0].text == ""
        assert regions[0].words == []
        # bbox should be zero-sized
        assert regions[0].bbox.width == 0
        assert regions[0].bbox.height == 0

    def test_line_with_word_missing_bounding_rect(self):
        """Word without bounding_rect should get zero bbox."""
        engine = OcrEngine()
        word = MagicMock()
        word.text = "ghost"
        word.bounding_rect = None  # simulate missing bbox
        # Need to also make hasattr return False for bounding_rect
        del word.bounding_rect
        line = _make_line("ghost", [word])

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions) == 1
        # Word should still be in list but with zero bbox
        assert len(regions[0].words) == 1
        assert regions[0].words[0].bbox.width == 0


class TestVeryLongLine:
    """Test with many words on a single line."""

    def test_long_line_bbox_is_union(self):
        engine = OcrEngine()
        # Create a line with 20 words spaced evenly
        words = []
        for i in range(20):
            x = i * 60
            words.append(_make_word(f"word{i}", x, 100, 50, 14))

        text = " ".join(f"word{i}" for i in range(20))
        line = _make_line(text, words)

        regions = engine._extract_regions_winocr([line], origin=None)

        assert len(regions) == 1
        bbox = regions[0].bbox
        assert bbox.x == 0
        assert bbox.y == 100
        # Last word: x=19*60=1140, width=50, so right edge=1190
        assert bbox.width == 1190
        assert bbox.height == 14
        assert len(regions[0].words) == 20


class TestOriginOffset:
    """Test that origin offset is correctly applied to all coordinates."""

    def test_offset_applied_to_words_and_line(self):
        engine = OcrEngine()
        word1 = _make_word("A", 0, 0, 20, 10)
        word2 = _make_word("B", 25, 0, 20, 10)
        line = _make_line("A B", [word1, word2])
        origin = Point(x=500, y=300)

        regions = engine._extract_regions_winocr([line], origin=origin)

        region = regions[0]
        # Line bbox should be offset
        assert region.bbox.x == 500
        assert region.bbox.y == 300
        # Words should also be offset
        assert region.words[0].bbox.x == 500
        assert region.words[0].bbox.y == 300
        assert region.words[1].bbox.x == 525
        assert region.words[1].bbox.y == 300

    def test_no_origin_means_no_offset(self):
        engine = OcrEngine()
        word = _make_word("X", 15, 25, 30, 12)
        line = _make_line("X", [word])

        regions = engine._extract_regions_winocr([line], origin=None)

        assert regions[0].bbox.x == 15
        assert regions[0].bbox.y == 25
        assert regions[0].words[0].bbox.x == 15
        assert regions[0].words[0].bbox.y == 25


class TestOcrRegionModelValidation:
    """Test that OcrRegion Pydantic model validates correctly."""

    def test_valid_region_creation(self):
        region = OcrRegion(
            text="Hello",
            bbox=Rect(x=10, y=20, width=50, height=15),
            confidence=0.95,
            words=[OcrWord(text="Hello", bbox=Rect(x=10, y=20, width=50, height=15), confidence=0.95)],
        )
        assert region.text == "Hello"
        assert region.bbox.width == 50
        assert len(region.words) == 1

    def test_region_model_dump(self):
        region = OcrRegion(
            text="Test",
            bbox=Rect(x=0, y=0, width=30, height=10),
            confidence=0.9,
            words=[],
        )
        d = region.model_dump()
        assert d["text"] == "Test"
        assert d["bbox"]["width"] == 30
        assert d["confidence"] == 0.9

    def test_region_default_values(self):
        region = OcrRegion(
            text="",
            bbox=Rect(x=0, y=0, width=0, height=0),
        )
        assert region.confidence == 0.0
        assert region.words == []
