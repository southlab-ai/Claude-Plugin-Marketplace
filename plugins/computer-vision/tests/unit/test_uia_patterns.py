"""Unit tests for UIA pattern wrappers — all 6 patterns mocked,
error taxonomy, and timeout handling.
"""

from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.errors import (
    ElementDisabledError,
    ElementOffscreenError,
    ElementUnresponsiveError,
    PatternNotSupportedError,
)
from src.utils import uia_patterns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(
    enabled: bool = True,
    rect: tuple = (0, 0, 100, 50),
    name: str = "TestBtn",
) -> MagicMock:
    """Create a mock IUIAutomationElement."""
    el = MagicMock()
    el.CurrentIsEnabled = enabled
    el.CurrentName = name

    rect_obj = MagicMock()
    rect_obj.left = rect[0]
    rect_obj.top = rect[1]
    rect_obj.right = rect[0] + rect[2]
    rect_obj.bottom = rect[1] + rect[3]
    el.CurrentBoundingRectangle = rect_obj

    return el


def _pattern_mock(element: MagicMock, pattern_id: int, pattern: MagicMock | None) -> None:
    """Configure element.GetCurrentPattern to return *pattern* for pattern_id."""
    original_side_effect = element.GetCurrentPattern.side_effect
    original_return = element.GetCurrentPattern.return_value

    def _get(pid: int) -> MagicMock | None:
        if pid == pattern_id:
            return pattern
        return None

    element.GetCurrentPattern.side_effect = _get


# ---------------------------------------------------------------------------
# InvokePattern
# ---------------------------------------------------------------------------

class TestInvoke:
    def test_invoke_success(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_INVOKE_PATTERN_ID, pat)

        uia_patterns.invoke(el)
        pat.Invoke.assert_called_once()

    def test_invoke_disabled_raises(self):
        el = _make_element(enabled=False)
        with pytest.raises(ElementDisabledError):
            uia_patterns.invoke(el)

    def test_invoke_offscreen_raises(self):
        el = _make_element(rect=(0, 0, 0, 0))
        el.GetCurrentPattern.return_value = None  # no ScrollItemPattern
        with pytest.raises(ElementOffscreenError):
            uia_patterns.invoke(el)

    def test_invoke_pattern_not_supported(self):
        el = _make_element()
        el.GetCurrentPattern.return_value = None
        with pytest.raises(PatternNotSupportedError):
            uia_patterns.invoke(el)


# ---------------------------------------------------------------------------
# ValuePattern
# ---------------------------------------------------------------------------

class TestSetValue:
    def test_set_value_success(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_VALUE_PATTERN_ID, pat)

        uia_patterns.set_value(el, "hello")
        pat.SetValue.assert_called_once_with("hello")

    def test_set_value_disabled_raises(self):
        el = _make_element(enabled=False)
        with pytest.raises(ElementDisabledError):
            uia_patterns.set_value(el, "text")


class TestGetValue:
    def test_get_value_success(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentValue = "world"
        _pattern_mock(el, uia_patterns.UIA_VALUE_PATTERN_ID, pat)

        result = uia_patterns.get_value(el)
        assert result == "world"

    def test_get_value_not_supported(self):
        el = _make_element()
        el.GetCurrentPattern.return_value = None
        with pytest.raises(PatternNotSupportedError):
            uia_patterns.get_value(el)


# ---------------------------------------------------------------------------
# TogglePattern
# ---------------------------------------------------------------------------

class TestToggle:
    def test_toggle_returns_new_state(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentToggleState = 1  # On
        _pattern_mock(el, uia_patterns.UIA_TOGGLE_PATTERN_ID, pat)

        result = uia_patterns.toggle(el)
        pat.Toggle.assert_called_once()
        assert result == 1

    def test_toggle_disabled_raises(self):
        el = _make_element(enabled=False)
        with pytest.raises(ElementDisabledError):
            uia_patterns.toggle(el)


class TestGetToggleState:
    def test_get_toggle_state(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentToggleState = 0  # Off
        _pattern_mock(el, uia_patterns.UIA_TOGGLE_PATTERN_ID, pat)

        result = uia_patterns.get_toggle_state(el)
        assert result == 0


# ---------------------------------------------------------------------------
# ExpandCollapsePattern
# ---------------------------------------------------------------------------

class TestExpand:
    def test_expand_success(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_EXPAND_COLLAPSE_PATTERN_ID, pat)

        uia_patterns.expand(el)
        pat.Expand.assert_called_once()

    def test_expand_disabled_raises(self):
        el = _make_element(enabled=False)
        with pytest.raises(ElementDisabledError):
            uia_patterns.expand(el)


class TestCollapse:
    def test_collapse_success(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_EXPAND_COLLAPSE_PATTERN_ID, pat)

        uia_patterns.collapse(el)
        pat.Collapse.assert_called_once()


class TestGetExpandState:
    def test_get_expand_state(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentExpandCollapseState = 2  # LeafNode
        _pattern_mock(el, uia_patterns.UIA_EXPAND_COLLAPSE_PATTERN_ID, pat)

        result = uia_patterns.get_expand_state(el)
        assert result == 2


# ---------------------------------------------------------------------------
# SelectionItemPattern
# ---------------------------------------------------------------------------

class TestSelect:
    def test_select_success(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_SELECTION_ITEM_PATTERN_ID, pat)

        uia_patterns.select(el)
        pat.Select.assert_called_once()

    def test_select_disabled_raises(self):
        el = _make_element(enabled=False)
        with pytest.raises(ElementDisabledError):
            uia_patterns.select(el)


class TestIsSelected:
    def test_is_selected_true(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentIsSelected = True
        _pattern_mock(el, uia_patterns.UIA_SELECTION_ITEM_PATTERN_ID, pat)

        result = uia_patterns.is_selected(el)
        assert result is True

    def test_is_selected_false(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentIsSelected = False
        _pattern_mock(el, uia_patterns.UIA_SELECTION_ITEM_PATTERN_ID, pat)

        result = uia_patterns.is_selected(el)
        assert result is False


# ---------------------------------------------------------------------------
# ScrollPattern
# ---------------------------------------------------------------------------

class TestScroll:
    def test_scroll_down_small(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_SCROLL_PATTERN_ID, pat)

        uia_patterns.scroll(el, "down", "small")
        pat.Scroll.assert_called_once_with(2, 4)  # NoAmount, SmallIncrement

    def test_scroll_up_large(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_SCROLL_PATTERN_ID, pat)

        uia_patterns.scroll(el, "up", "large")
        pat.Scroll.assert_called_once_with(2, 0)  # NoAmount, LargeDecrement

    def test_scroll_left_small(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_SCROLL_PATTERN_ID, pat)

        uia_patterns.scroll(el, "left", "small")
        pat.Scroll.assert_called_once_with(1, 2)  # SmallDecrement, NoAmount

    def test_scroll_right_large(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_SCROLL_PATTERN_ID, pat)

        uia_patterns.scroll(el, "right", "large")
        pat.Scroll.assert_called_once_with(3, 2)  # LargeIncrement, NoAmount


class TestGetScrollPercent:
    def test_get_scroll_percent(self):
        el = _make_element()
        pat = MagicMock()
        pat.CurrentHorizontalScrollPercent = 25.0
        pat.CurrentVerticalScrollPercent = 75.0
        _pattern_mock(el, uia_patterns.UIA_SCROLL_PATTERN_ID, pat)

        result = uia_patterns.get_scroll_percent(el)
        assert result == (25.0, 75.0)


# ---------------------------------------------------------------------------
# get_supported_patterns
# ---------------------------------------------------------------------------

class TestGetSupportedPatterns:
    def test_all_patterns_supported(self):
        el = _make_element()
        el.GetCurrentPattern.return_value = MagicMock()

        result = uia_patterns.get_supported_patterns(el)
        assert len(result) == 6
        assert "InvokePattern" in result
        assert "TogglePattern" in result

    def test_no_patterns_supported(self):
        el = _make_element()
        el.GetCurrentPattern.return_value = None

        result = uia_patterns.get_supported_patterns(el)
        assert result == []

    def test_some_patterns_supported(self):
        el = _make_element()

        def _selective(pid: int) -> MagicMock | None:
            if pid == uia_patterns.UIA_INVOKE_PATTERN_ID:
                return MagicMock()
            if pid == uia_patterns.UIA_TOGGLE_PATTERN_ID:
                return MagicMock()
            return None

        el.GetCurrentPattern.side_effect = _selective

        result = uia_patterns.get_supported_patterns(el)
        assert set(result) == {"InvokePattern", "TogglePattern"}


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestDirectCalls:
    """Pattern wrappers call COM directly (no threading) to avoid STA deadlocks."""

    def test_invoke_calls_directly(self):
        el = _make_element()
        pat = MagicMock()
        _pattern_mock(el, uia_patterns.UIA_INVOKE_PATTERN_ID, pat)

        uia_patterns.invoke(el)
        pat.Invoke.assert_called_once()

    def test_invoke_propagates_com_error(self):
        el = _make_element()
        pat = MagicMock()
        pat.Invoke.side_effect = OSError("COM error")
        _pattern_mock(el, uia_patterns.UIA_INVOKE_PATTERN_ID, pat)

        with pytest.raises(OSError):
            uia_patterns.invoke(el)


# ---------------------------------------------------------------------------
# ScrollIntoView fallback
# ---------------------------------------------------------------------------

class TestScrollIntoViewFallback:
    def test_offscreen_scrolled_into_view(self):
        el = _make_element(rect=(0, 0, 0, 0))

        # First call to BoundingRectangle returns empty rect
        # After ScrollIntoView, second call returns valid rect
        call_count = [0]
        valid_rect = MagicMock()
        valid_rect.left = 10
        valid_rect.top = 20
        valid_rect.right = 110
        valid_rect.bottom = 70

        empty_rect = MagicMock()
        empty_rect.left = 0
        empty_rect.top = 0
        empty_rect.right = 0
        empty_rect.bottom = 0

        def _get_rect() -> MagicMock:
            call_count[0] += 1
            if call_count[0] <= 1:
                return empty_rect
            return valid_rect

        type(el).CurrentBoundingRectangle = PropertyMock(side_effect=_get_rect)

        scroll_item = MagicMock()

        def _get_pattern(pid: int) -> MagicMock | None:
            if pid == uia_patterns._UIA_SCROLL_ITEM_PATTERN_ID:
                return scroll_item
            if pid == uia_patterns.UIA_INVOKE_PATTERN_ID:
                return MagicMock()
            return None

        el.GetCurrentPattern.side_effect = _get_pattern

        # Should succeed because ScrollIntoView makes rect valid
        uia_patterns.invoke(el)
        scroll_item.ScrollIntoView.assert_called_once()

    def test_offscreen_no_scroll_item_raises(self):
        el = _make_element(rect=(0, 0, 0, 0))
        el.GetCurrentPattern.return_value = None

        with pytest.raises(ElementOffscreenError):
            uia_patterns.invoke(el)
