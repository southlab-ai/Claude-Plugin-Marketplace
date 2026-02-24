"""Unit tests for fuzzy matching logic in src/tools/find.py.

Tests edge cases for _fuzzy_score, _match_uia, and related helpers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models import Rect, UiaElement
from src.tools.find import (
    _fuzzy_score,
    _flatten_uia_tree,
    _MATCH_THRESHOLD,
    _SUBSTRING_SCORE,
)


# ===========================================================================
# _fuzzy_score tests
# ===========================================================================

class TestFuzzyScore:
    """Tests for the _fuzzy_score helper."""

    def test_empty_query_returns_zero(self):
        assert _fuzzy_score("", "Submit") == 0.0

    def test_empty_text_returns_zero(self):
        assert _fuzzy_score("Submit", "") == 0.0

    def test_both_empty_returns_zero(self):
        assert _fuzzy_score("", "") == 0.0

    def test_exact_match_returns_high_score(self):
        score = _fuzzy_score("Submit", "Submit")
        assert score >= 0.9

    def test_case_insensitive(self):
        score = _fuzzy_score("submit", "Submit")
        assert score >= _SUBSTRING_SCORE  # substring match

    def test_substring_match_returns_at_least_substring_score(self):
        score = _fuzzy_score("sub", "Submit")
        assert score >= _SUBSTRING_SCORE

    def test_no_match_returns_low_score(self):
        score = _fuzzy_score("xyzabc", "Submit")
        assert score < _MATCH_THRESHOLD

    def test_single_character_query(self):
        # Single char "S" is substring of "Submit"
        score = _fuzzy_score("S", "Submit")
        # "s" in "submit" -> substring match
        assert score >= _SUBSTRING_SCORE

    def test_single_character_no_match(self):
        score = _fuzzy_score("z", "Submit")
        assert score < _MATCH_THRESHOLD

    def test_threshold_boundary_below(self):
        """Score just below threshold should not qualify."""
        # Use strings that produce a ratio just below 0.5
        # "abcde" vs "vwxyz" -- completely different
        score = _fuzzy_score("abcde", "vwxyz")
        assert score < _MATCH_THRESHOLD

    def test_threshold_boundary_above(self):
        """Score at or above threshold should qualify."""
        # "abc" vs "abd" -- very similar
        score = _fuzzy_score("abc", "abd")
        assert score >= _MATCH_THRESHOLD

    # --- Unicode ---

    def test_unicode_cjk(self):
        score = _fuzzy_score("提交", "提交订单")
        assert score >= _SUBSTRING_SCORE

    def test_unicode_emoji(self):
        score = _fuzzy_score("🔍", "🔍 Search")
        assert score >= _SUBSTRING_SCORE

    def test_unicode_accented(self):
        score = _fuzzy_score("café", "Café Menu")
        assert score >= _SUBSTRING_SCORE

    # --- Special characters ---

    def test_special_characters_brackets(self):
        score = _fuzzy_score("[OK]", "[OK] Button")
        assert score >= _SUBSTRING_SCORE

    def test_special_characters_ampersand(self):
        score = _fuzzy_score("Save & Exit", "Save & Exit")
        assert score >= 0.9

    def test_special_characters_dots(self):
        score = _fuzzy_score("file.txt", "Open file.txt")
        assert score >= _SUBSTRING_SCORE

    def test_whitespace_handling(self):
        score = _fuzzy_score("Save As", "Save As...")
        assert score >= _SUBSTRING_SCORE

    def test_numeric_string(self):
        score = _fuzzy_score("123", "Page 123 of 456")
        assert score >= _SUBSTRING_SCORE


# ===========================================================================
# Control type matching (tested through _match_uia indirectly)
# ===========================================================================

class TestControlTypeMatching:
    """Tests for control type matching in _match_uia."""

    @pytest.fixture(autouse=True)
    def _patch_security(self):
        with (
            patch("src.tools.find.validate_hwnd_range"),
            patch("src.tools.find.validate_hwnd_fresh", return_value=True),
            patch("src.tools.find.check_restricted"),
            patch("src.tools.find._get_process_name_from_hwnd", return_value="notepad"),
            patch("src.tools.find.log_action"),
            patch("src.tools.find.win32gui.GetWindowRect", return_value=(0, 0, 1920, 1080)),
        ):
            yield

    @patch("src.tools.find.get_ui_tree")
    def test_query_matches_control_type_exact(self, mock_tree):
        """Query that exactly matches a control type should get boosted."""
        from src.tools.find import _match_uia

        mock_tree.return_value = [
            UiaElement(
                ref_id="ref_1",
                name="",
                control_type="Button",
                rect=Rect(x=100, y=100, width=80, height=30),
            ),
        ]

        matches = _match_uia("Button", 12345)
        assert len(matches) >= 1
        assert matches[0].control_type == "Button"

    @patch("src.tools.find.get_ui_tree")
    def test_query_matches_control_type_case_insensitive(self, mock_tree):
        from src.tools.find import _match_uia

        mock_tree.return_value = [
            UiaElement(
                ref_id="ref_1",
                name="",
                control_type="Button",
                rect=Rect(x=100, y=100, width=80, height=30),
            ),
        ]

        matches = _match_uia("button", 12345)
        assert len(matches) >= 1

    @patch("src.tools.find.get_ui_tree")
    def test_query_partial_control_type(self, mock_tree):
        """Query that is a substring of control type should match."""
        from src.tools.find import _match_uia

        mock_tree.return_value = [
            UiaElement(
                ref_id="ref_1",
                name="",
                control_type="MenuItem",
                rect=Rect(x=100, y=100, width=80, height=30),
            ),
        ]

        matches = _match_uia("Menu", 12345)
        assert len(matches) >= 1

    @patch("src.tools.find.get_ui_tree")
    def test_zero_size_elements_skipped(self, mock_tree):
        """Elements with zero-size bounding boxes should be skipped."""
        from src.tools.find import _match_uia

        mock_tree.return_value = [
            UiaElement(
                ref_id="ref_1",
                name="Submit",
                control_type="Button",
                rect=Rect(x=0, y=0, width=0, height=0),
            ),
        ]

        matches = _match_uia("Submit", 12345)
        assert len(matches) == 0


# ===========================================================================
# _flatten_uia_tree tests
# ===========================================================================

class TestFlattenUiaTree:
    """Tests for the tree flattening helper."""

    def test_empty_tree(self):
        assert _flatten_uia_tree([]) == []

    def test_flat_list(self):
        elements = [
            UiaElement(ref_id="ref_1", name="A", control_type="Button", rect=Rect(x=0, y=0, width=1, height=1)),
            UiaElement(ref_id="ref_2", name="B", control_type="Button", rect=Rect(x=0, y=0, width=1, height=1)),
        ]
        flat = _flatten_uia_tree(elements)
        assert len(flat) == 2

    def test_nested_tree(self):
        child = UiaElement(ref_id="ref_2", name="Child", control_type="Button", rect=Rect(x=0, y=0, width=1, height=1))
        parent = UiaElement(
            ref_id="ref_1",
            name="Parent",
            control_type="Pane",
            rect=Rect(x=0, y=0, width=1, height=1),
            children=[child],
        )
        flat = _flatten_uia_tree([parent])
        assert len(flat) == 2
        assert flat[0].name == "Parent"
        assert flat[1].name == "Child"

    def test_deeply_nested_tree(self):
        leaf = UiaElement(ref_id="ref_3", name="Leaf", control_type="Button", rect=Rect(x=0, y=0, width=1, height=1))
        mid = UiaElement(
            ref_id="ref_2",
            name="Mid",
            control_type="Group",
            rect=Rect(x=0, y=0, width=1, height=1),
            children=[leaf],
        )
        root = UiaElement(
            ref_id="ref_1",
            name="Root",
            control_type="Window",
            rect=Rect(x=0, y=0, width=1, height=1),
            children=[mid],
        )
        flat = _flatten_uia_tree([root])
        assert len(flat) == 3
        names = [e.name for e in flat]
        assert names == ["Root", "Mid", "Leaf"]

    def test_multiple_children(self):
        children = [
            UiaElement(ref_id=f"ref_{i}", name=f"C{i}", control_type="Button", rect=Rect(x=0, y=0, width=1, height=1))
            for i in range(5)
        ]
        parent = UiaElement(
            ref_id="ref_0",
            name="Parent",
            control_type="Pane",
            rect=Rect(x=0, y=0, width=1, height=1),
            children=children,
        )
        flat = _flatten_uia_tree([parent])
        assert len(flat) == 6  # parent + 5 children
