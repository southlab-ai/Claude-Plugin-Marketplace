"""Unit tests for cv_find tool in src/tools/find.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models import FindMatch, OcrRegion, Rect, UiaElement


# ---------------------------------------------------------------------------
# Helpers to build mock UIA elements
# ---------------------------------------------------------------------------

def _make_uia_element(
    name: str = "",
    control_type: str = "Button",
    ref_id: str = "ref_1",
    value: str | None = None,
    rect: Rect | None = None,
    children: list | None = None,
) -> UiaElement:
    return UiaElement(
        ref_id=ref_id,
        name=name,
        control_type=control_type,
        rect=rect or Rect(x=100, y=100, width=80, height=30),
        value=value,
        children=children or [],
    )


# Window rect that wraps all test elements: (0, 0, 1920, 1080)
MOCK_WINDOW_RECT = (0, 0, 1920, 1080)


# ---------------------------------------------------------------------------
# Patches applied to every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_security_and_win32():
    """Patch security gates and win32 calls so tests run without a real desktop."""
    with (
        patch("src.tools.find.validate_hwnd_range"),
        patch("src.tools.find.validate_hwnd_fresh", return_value=True),
        patch("src.tools.find.check_restricted"),
        patch("src.tools.find._get_process_name_from_hwnd", return_value="notepad"),
        patch("src.tools.find.log_action"),
        patch("src.tools.find.win32gui.GetWindowRect", return_value=MOCK_WINDOW_RECT),
    ):
        yield


# ===========================================================================
# Test: UIA matching
# ===========================================================================

class TestCvFindUia:
    """Tests for cv_find using UIA matching."""

    @patch("src.tools.find.get_ui_tree")
    def test_uia_finds_exact_name(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Submit", control_type="Button", ref_id="ref_1"),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="uia")

        assert result["success"] is True
        assert result["match_count"] >= 1
        assert result["matches"][0]["text"] == "Submit"
        assert result["matches"][0]["source"] == "uia"

    @patch("src.tools.find.get_ui_tree")
    def test_uia_fuzzy_match(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Submit Order", control_type="Button", ref_id="ref_1"),
        ]

        result = cv_find(query="submit", hwnd=12345, method="uia")

        assert result["success"] is True
        assert result["match_count"] >= 1

    @patch("src.tools.find.get_ui_tree")
    def test_uia_no_match(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Cancel", control_type="Button", ref_id="ref_1"),
        ]

        result = cv_find(query="xyznonexistent", hwnd=12345, method="uia")

        assert result["success"] is False
        assert result["error"]["code"] == "FIND_NO_MATCH"

    @patch("src.tools.find.get_ui_tree")
    def test_uia_matches_control_type(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="", control_type="Button", ref_id="ref_1"),
            _make_uia_element(name="", control_type="Edit", ref_id="ref_2"),
        ]

        result = cv_find(query="Button", hwnd=12345, method="uia")

        assert result["success"] is True
        # Should find the Button element
        found_types = [m["control_type"] for m in result["matches"]]
        assert "Button" in found_types

    @patch("src.tools.find.get_ui_tree")
    def test_uia_matches_value(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(
                name="Search",
                control_type="Edit",
                ref_id="ref_1",
                value="hello world",
            ),
        ]

        result = cv_find(query="hello world", hwnd=12345, method="uia")

        assert result["success"] is True
        assert result["match_count"] >= 1

    @patch("src.tools.find.get_ui_tree")
    def test_uia_flattens_nested_tree(self, mock_tree):
        from src.tools.find import cv_find

        child = _make_uia_element(name="Deep Button", control_type="Button", ref_id="ref_2")
        parent = _make_uia_element(
            name="Toolbar",
            control_type="Pane",
            ref_id="ref_1",
            children=[child],
        )
        mock_tree.return_value = [parent]

        result = cv_find(query="Deep Button", hwnd=12345, method="uia")

        assert result["success"] is True
        assert any(m["text"] == "Deep Button" for m in result["matches"])


# ===========================================================================
# Test: OCR matching
# ===========================================================================

class TestCvFindOcr:
    """Tests for cv_find using OCR matching."""

    def test_ocr_finds_text(self):
        from src.tools.find import cv_find

        mock_engine = MagicMock()
        mock_engine.recognize.return_value = {
            "text": "Submit Order",
            "regions": [
                OcrRegion(
                    text="Submit Order",
                    bbox=Rect(x=200, y=300, width=100, height=20),
                    confidence=0.95,
                ),
            ],
            "engine": "winocr",
            "confidence": 0.95,
            "language": "en-US",
            "origin": None,
        }

        # Patch the OcrEngine singleton and screenshot capture inside _match_ocr
        with (
            patch("src.utils.ocr_engine._engine", mock_engine),
            patch("src.utils.screenshot.capture_window_raw", return_value=MagicMock()),
        ):
            result = cv_find(query="Submit", hwnd=12345, method="ocr")

        assert result["success"] is True
        assert result["match_count"] >= 1
        assert result["matches"][0]["source"] == "ocr"

    def test_ocr_no_match(self):
        from src.tools.find import cv_find

        mock_engine = MagicMock()
        mock_engine.recognize.return_value = {
            "text": "Cancel",
            "regions": [
                OcrRegion(
                    text="Cancel",
                    bbox=Rect(x=200, y=300, width=60, height=20),
                    confidence=0.9,
                ),
            ],
            "engine": "winocr",
            "confidence": 0.9,
            "language": "en-US",
            "origin": None,
        }

        with (
            patch("src.utils.ocr_engine._engine", mock_engine),
            patch("src.utils.screenshot.capture_window_raw", return_value=MagicMock()),
        ):
            result = cv_find(query="xyznonexistent", hwnd=12345, method="ocr")

        assert result["success"] is False
        assert result["error"]["code"] == "FIND_NO_MATCH"


# ===========================================================================
# Test: Auto mode (UIA first, OCR fallback)
# ===========================================================================

class TestCvFindAuto:
    """Tests for cv_find in auto mode."""

    @patch("src.tools.find.get_ui_tree")
    def test_auto_uses_uia_when_found(self, mock_tree):
        """When UIA finds results, OCR should NOT be called."""
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Submit", control_type="Button", ref_id="ref_1"),
        ]

        # We don't patch _match_ocr so if it runs, it would fail or import OcrEngine.
        # Instead, patch at module level to detect calls.
        with patch("src.tools.find._match_ocr") as mock_ocr:
            mock_ocr.return_value = []
            result = cv_find(query="Submit", hwnd=12345, method="auto")

            assert result["success"] is True
            assert result["method_used"] == "uia"
            mock_ocr.assert_not_called()

    @patch("src.tools.find._match_ocr")
    @patch("src.tools.find.get_ui_tree")
    def test_auto_falls_back_to_ocr(self, mock_tree, mock_ocr):
        """When UIA returns nothing, OCR should be tried."""
        from src.tools.find import cv_find

        mock_tree.return_value = []  # Empty UIA tree
        mock_ocr.return_value = [
            FindMatch(
                text="Submit",
                bbox=Rect(x=200, y=300, width=100, height=20),
                confidence=0.8,
                source="ocr",
                ref_id="ocr_0",
                control_type=None,
            ),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="auto")

        assert result["success"] is True
        assert result["method_used"] == "ocr"
        mock_ocr.assert_called_once()


# ===========================================================================
# Test: Bbox validation
# ===========================================================================

class TestCvFindBboxValidation:
    """Tests for bbox validation filtering."""

    @patch("src.tools.find.get_ui_tree")
    def test_bbox_outside_window_rejected(self, mock_tree):
        """Matches with bbox outside the window bounds should be filtered out."""
        from src.tools.find import cv_find

        # Window is at (0, 0, 1920, 1080) per MOCK_WINDOW_RECT
        # Element is at (3000, 3000) -- outside
        mock_tree.return_value = [
            _make_uia_element(
                name="Submit",
                control_type="Button",
                ref_id="ref_1",
                rect=Rect(x=3000, y=3000, width=80, height=30),
            ),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="uia")

        assert result["success"] is False
        assert result["error"]["code"] == "FIND_NO_MATCH"

    @patch("src.tools.find.get_ui_tree")
    def test_bbox_inside_window_kept(self, mock_tree):
        """Matches with bbox inside the window bounds should be kept."""
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(
                name="Submit",
                control_type="Button",
                ref_id="ref_1",
                rect=Rect(x=100, y=100, width=80, height=30),
            ),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="uia")

        assert result["success"] is True
        assert result["match_count"] >= 1


# ===========================================================================
# Test: Input validation
# ===========================================================================

class TestCvFindInputValidation:
    """Tests for input validation."""

    def test_invalid_method(self):
        from src.tools.find import cv_find

        result = cv_find(query="test", hwnd=12345, method="invalid")

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_INPUT"

    def test_empty_query(self):
        from src.tools.find import cv_find

        result = cv_find(query="", hwnd=12345)

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_INPUT"

    def test_whitespace_only_query(self):
        from src.tools.find import cv_find

        result = cv_find(query="   ", hwnd=12345)

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_INPUT"

    @patch("src.tools.find.get_ui_tree")
    def test_query_capped_at_500(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = []
        long_query = "a" * 600

        # Should not error due to long query -- just gets truncated
        result = cv_find(query=long_query, hwnd=12345, method="uia")

        # No match is fine, just testing it doesn't crash
        assert "error" in result or "success" in result

    @patch("src.tools.find.get_ui_tree")
    def test_max_results_capped(self, mock_tree):
        from src.tools.find import cv_find

        # Return many elements
        elements = [
            _make_uia_element(name=f"Button {i}", control_type="Button", ref_id=f"ref_{i}")
            for i in range(30)
        ]
        mock_tree.return_value = elements

        result = cv_find(query="Button", hwnd=12345, method="uia", max_results=5)

        assert result["success"] is True
        assert len(result["matches"]) <= 5

    @patch("src.tools.find.get_ui_tree")
    def test_max_results_floor_at_1(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Submit", control_type="Button", ref_id="ref_1"),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="uia", max_results=-10)

        assert result["success"] is True
        assert len(result["matches"]) >= 1


# ===========================================================================
# Test: Security gates
# ===========================================================================

class TestCvFindSecurity:
    """Tests verifying security gates are invoked."""

    def test_invalid_hwnd_range(self):
        """Invalid HWND should be rejected before any search."""
        from src.tools.find import cv_find

        with patch("src.tools.find.validate_hwnd_range", side_effect=ValueError("Invalid HWND: 0")):
            result = cv_find(query="test", hwnd=0)

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_INPUT"

    def test_stale_hwnd_rejected(self):
        from src.tools.find import cv_find

        with patch("src.tools.find.validate_hwnd_fresh", return_value=False):
            result = cv_find(query="test", hwnd=99999)

        assert result["success"] is False
        assert "no longer valid" in result["error"]["message"]

    def test_restricted_process_rejected(self):
        from src.tools.find import cv_find

        with patch(
            "src.tools.find.check_restricted",
            side_effect=Exception("Access denied: process 'keepass' is restricted"),
        ):
            result = cv_find(query="test", hwnd=12345)

        assert result["success"] is False

    @patch("src.tools.find.get_ui_tree")
    def test_log_action_called(self, mock_tree):
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="OK", control_type="Button", ref_id="ref_1"),
        ]

        with patch("src.tools.find.log_action") as mock_log:
            cv_find(query="OK", hwnd=12345, method="uia")
            mock_log.assert_called_once()
