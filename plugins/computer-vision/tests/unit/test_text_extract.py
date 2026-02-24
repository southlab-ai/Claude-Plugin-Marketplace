"""Unit tests for cv_get_text tool in src/tools/text_extract.py."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.models import Rect, UiaElement


# --- Helper factories ---

def _make_element(
    name: str = "",
    control_type: str = "Text",
    x: int = 0,
    y: int = 0,
    width: int = 100,
    height: int = 20,
    value: str | None = None,
    is_password: bool = False,
    children: list | None = None,
) -> UiaElement:
    """Create a UiaElement for testing."""
    return UiaElement(
        ref_id="ref_1",
        name=name,
        control_type=control_type,
        rect=Rect(x=x, y=y, width=width, height=height),
        value=value,
        is_enabled=True,
        is_interactive=False,
        is_password=is_password,
        children=children or [],
    )


# --- UIA text extraction ---

class TestExtractUiaText:
    """Tests for _extract_uia_text helper."""

    @patch("src.tools.text_extract.get_ui_tree")
    def test_basic_text_elements(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="Hello", control_type="Text", y=0, x=0),
            _make_element(name="World", control_type="Text", y=0, x=100),
        ]
        text, confidence = _extract_uia_text(12345)
        assert "Hello" in text
        assert "World" in text
        assert confidence == 1.0

    @patch("src.tools.text_extract.get_ui_tree")
    def test_edit_prefers_value_over_name(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(
                name="Placeholder text",
                control_type="Edit",
                value="Actual typed content",
                y=0, x=0,
            ),
        ]
        text, _ = _extract_uia_text(12345)
        assert "Actual typed content" in text
        assert "Placeholder text" not in text

    @patch("src.tools.text_extract.get_ui_tree")
    def test_edit_falls_back_to_name_when_value_empty(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(
                name="Search box",
                control_type="Edit",
                value=None,
                y=0, x=0,
            ),
        ]
        text, _ = _extract_uia_text(12345)
        assert "Search box" in text

    @patch("src.tools.text_extract.get_ui_tree")
    def test_non_text_control_types_ignored(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="OK", control_type="Button", y=0, x=0),
            _make_element(name="Visible text", control_type="Text", y=0, x=100),
        ]
        text, _ = _extract_uia_text(12345)
        assert "Visible text" in text
        assert "OK" not in text

    @patch("src.tools.text_extract.get_ui_tree")
    def test_empty_name_elements_skipped(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="", control_type="Text", y=0, x=0),
            _make_element(name="Content", control_type="Text", y=0, x=100),
        ]
        text, _ = _extract_uia_text(12345)
        assert text.strip() == "Content"

    @patch("src.tools.text_extract.get_ui_tree")
    def test_empty_tree_returns_empty_string(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = []
        text, confidence = _extract_uia_text(12345)
        assert text == ""
        assert confidence == 1.0


# --- Spatial sorting ---

class TestSpatialSorting:
    """Tests for spatial sorting in UIA text extraction."""

    @patch("src.tools.text_extract.get_ui_tree")
    def test_top_to_bottom_left_to_right(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="Bottom-Right", control_type="Text", y=100, x=200),
            _make_element(name="Top-Left", control_type="Text", y=0, x=0),
            _make_element(name="Top-Right", control_type="Text", y=0, x=200),
            _make_element(name="Bottom-Left", control_type="Text", y=100, x=0),
        ]
        text, _ = _extract_uia_text(12345)
        lines = [line for line in text.split("\n") if line.strip()]
        # Top row should come before bottom row
        top_left_idx = text.index("Top-Left")
        bottom_left_idx = text.index("Bottom-Left")
        assert top_left_idx < bottom_left_idx

        # Within same row, left should come before right
        top_right_idx = text.index("Top-Right")
        assert top_left_idx < top_right_idx

    @patch("src.tools.text_extract.get_ui_tree")
    def test_same_row_grouping(self, mock_tree):
        """Elements within _ROW_HEIGHT pixels of each other should be on the same logical row."""
        from src.tools.text_extract import _extract_uia_text

        # y=5 and y=10 are both in row 0 (y//20 == 0)
        mock_tree.return_value = [
            _make_element(name="B", control_type="Text", y=10, x=200),
            _make_element(name="A", control_type="Text", y=5, x=0),
        ]
        text, _ = _extract_uia_text(12345)
        a_idx = text.index("A")
        b_idx = text.index("B")
        assert a_idx < b_idx


# --- Paragraph breaks ---

class TestParagraphBreaks:
    """Tests for paragraph break insertion when y-gap > 40px."""

    @patch("src.tools.text_extract.get_ui_tree")
    def test_large_y_gap_inserts_paragraph_break(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="Section 1", control_type="Text", y=0, x=0),
            _make_element(name="Section 2", control_type="Text", y=100, x=0),
        ]
        text, _ = _extract_uia_text(12345)
        # Should have a double newline (paragraph break) between sections
        assert "\n\n" in text

    @patch("src.tools.text_extract.get_ui_tree")
    def test_small_y_gap_no_paragraph_break(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(name="Line 1", control_type="Text", y=0, x=0),
            _make_element(name="Line 2", control_type="Text", y=25, x=0),
        ]
        text, _ = _extract_uia_text(12345)
        # Should NOT have a double newline — gap is only 25px
        assert "\n\n" not in text
        assert "Line 1\nLine 2" in text


# --- Password redaction ---

class TestPasswordRedaction:
    """Tests for password field handling."""

    @patch("src.tools.text_extract.get_ui_tree")
    def test_password_field_shows_redacted(self, mock_tree):
        from src.tools.text_extract import _extract_uia_text

        mock_tree.return_value = [
            _make_element(
                name="Password",
                control_type="Edit",
                value="[PASSWORD]",
                is_password=True,
                y=0, x=0,
            ),
        ]
        text, _ = _extract_uia_text(12345)
        assert "[PASSWORD]" in text
        assert "secret" not in text


# --- Nested children ---

class TestFlattenTree:
    """Tests for tree flattening."""

    def test_flatten_nested_tree(self):
        from src.tools.text_extract import _flatten_uia_tree

        child = _make_element(name="Child", control_type="Text")
        grandchild = _make_element(name="Grandchild", control_type="Text")
        child_with_gc = _make_element(name="Parent", control_type="Text", children=[grandchild])
        root = [_make_element(name="Root", control_type="Text", children=[child, child_with_gc])]

        flat = _flatten_uia_tree(root)
        names = [el.name for el in flat]
        assert "Root" in names
        assert "Child" in names
        assert "Parent" in names
        assert "Grandchild" in names
        assert len(flat) == 4

    def test_flatten_empty_tree(self):
        from src.tools.text_extract import _flatten_uia_tree

        assert _flatten_uia_tree([]) == []


# --- OCR fallback ---

class TestOcrFallback:
    """Tests for auto mode OCR fallback when UIA returns insufficient text."""

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_ocr_text")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_auto_falls_back_to_ocr_when_uia_short(
        self, mock_gwtp, mock_uia, mock_ocr, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_uia.return_value = ("Hi", 1.0)  # < 20 chars
        mock_ocr.return_value = ("Full OCR text from the window content", 0.85)

        result = cv_get_text(12345, method="auto")
        assert result["success"] is True
        assert result["source"] == "ocr"
        assert "Full OCR text" in result["text"]
        mock_ocr.assert_called_once()

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_ocr_text")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_auto_uses_uia_when_sufficient(
        self, mock_gwtp, mock_uia, mock_ocr, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_uia.return_value = ("This is plenty of UIA text content here", 1.0)

        result = cv_get_text(12345, method="auto")
        assert result["success"] is True
        assert result["source"] == "uia"
        mock_ocr.assert_not_called()


# --- PII redaction ---

class TestPiiRedaction:
    """Tests for PII pattern redaction on output text."""

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_ssn_redacted_from_uia_output(
        self, mock_gwtp, mock_uia, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = [r"\b\d{3}-\d{2}-\d{4}\b"]
        mock_uia.return_value = ("SSN: 123-45-6789 is private", 1.0)

        result = cv_get_text(12345, method="uia")
        assert result["success"] is True
        assert "123-45-6789" not in result["text"]
        assert "[REDACTED]" in result["text"]

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_ocr_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_credit_card_redacted_from_ocr_output(
        self, mock_gwtp, mock_ocr, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = [r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"]
        mock_ocr.return_value = ("Card: 4111-1111-1111-1111 on file", 0.9)

        result = cv_get_text(12345, method="ocr")
        assert result["success"] is True
        assert "4111-1111-1111-1111" not in result["text"]
        assert "[REDACTED]" in result["text"]


# --- Security gates ---

class TestSecurityGates:
    """Tests for security validation in cv_get_text."""

    def test_invalid_hwnd_range(self):
        from src.tools.text_extract import cv_get_text

        result = cv_get_text(0)
        assert result["success"] is False
        assert "Invalid HWND" in result["error"]["message"]

    def test_negative_hwnd(self):
        from src.tools.text_extract import cv_get_text

        result = cv_get_text(-1)
        assert result["success"] is False

    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=False)
    def test_stale_hwnd(self, mock_fresh, mock_range):
        from src.tools.text_extract import cv_get_text

        result = cv_get_text(99999)
        assert result["success"] is False
        assert result["error"]["code"] == "WINDOW_NOT_FOUND"

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_security_functions_called(
        self, mock_gwtp, mock_uia, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_uia.return_value = ("Enough text for UIA to pass threshold", 1.0)

        cv_get_text(12345)
        mock_range.assert_called_once_with(12345)
        mock_fresh.assert_called_once_with(12345)
        mock_restricted.assert_called_once_with("notepad")
        assert mock_log.call_count >= 1

    def test_invalid_method_parameter(self):
        from src.tools.text_extract import cv_get_text

        result = cv_get_text(12345, method="invalid")
        assert result["success"] is False
        assert "Invalid method" in result["error"]["message"]


# --- Method parameter ---

class TestMethodParameter:
    """Tests for explicit method selection."""

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_ocr_text")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_method_uia_forces_uia_only(
        self, mock_gwtp, mock_uia, mock_ocr, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_uia.return_value = ("Short", 1.0)  # < 20 chars but method is forced

        result = cv_get_text(12345, method="uia")
        assert result["success"] is True
        assert result["source"] == "uia"
        mock_ocr.assert_not_called()

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="chrome")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_ocr_text")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 5678))
    def test_method_ocr_forces_ocr_only(
        self, mock_gwtp, mock_uia, mock_ocr, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_ocr.return_value = ("OCR extracted text from the window", 0.9)

        result = cv_get_text(12345, method="ocr")
        assert result["success"] is True
        assert result["source"] == "ocr"
        mock_uia.assert_not_called()


# --- Return structure ---

class TestReturnStructure:
    """Tests for correct return format."""

    @patch("src.tools.text_extract.log_action")
    @patch("src.tools.text_extract.get_process_name_by_pid", return_value="notepad")
    @patch("src.tools.text_extract.check_restricted")
    @patch("src.tools.text_extract.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.text_extract.validate_hwnd_range")
    @patch("src.tools.text_extract.config")
    @patch("src.tools.text_extract._extract_uia_text")
    @patch("win32process.GetWindowThreadProcessId", return_value=(0, 1234))
    def test_success_response_fields(
        self, mock_gwtp, mock_uia, mock_config,
        mock_range, mock_fresh, mock_restricted, mock_procname, mock_log,
    ):
        from src.tools.text_extract import cv_get_text

        mock_config.OCR_REDACTION_PATTERNS = []
        mock_uia.return_value = ("Line 1\nLine 2\nLine 3", 1.0)

        result = cv_get_text(12345, method="uia")
        assert result["success"] is True
        assert result["text"] == "Line 1\nLine 2\nLine 3"
        assert result["source"] == "uia"
        assert result["line_count"] == 3
        assert result["confidence"] == 1.0
