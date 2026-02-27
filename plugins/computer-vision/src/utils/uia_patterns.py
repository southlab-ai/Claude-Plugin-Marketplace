"""UIA pattern invocation wrappers with error taxonomy.

Each wrapper:
1. Checks CurrentIsEnabled -> ElementDisabledError
2. Checks BoundingRectangle -> attempts ScrollIntoView, raises ElementOffscreenError
3. Calls GetCurrentPattern + QueryInterface -> PatternNotSupportedError
4. Executes the pattern method
5. COM pointer cleanup handled by comtypes RAII (no explicit Release)

NOTE: All COM calls are made directly on the caller's thread (no worker threads).
comtypes initializes COM as STA, so dispatching to worker threads causes
cross-apartment marshaling deadlocks. The outer cv_action timeout budget
provides the safety net for hung COM calls.
"""

from __future__ import annotations

import logging
from typing import Any

from src.errors import (
    ElementDisabledError,
    ElementOffscreenError,
    PatternNotSupportedError,
)
from src.utils.uia import (
    UIA_INVOKE_PATTERN_ID,
    UIA_VALUE_PATTERN_ID,
    UIA_SCROLL_PATTERN_ID,
    UIA_EXPAND_COLLAPSE_PATTERN_ID,
    UIA_SELECTION_ITEM_PATTERN_ID,
    UIA_TOGGLE_PATTERN_ID,
)

logger = logging.getLogger(__name__)

# ScrollItemPattern ID (not in uia.py but needed for scroll-into-view)
_UIA_SCROLL_ITEM_PATTERN_ID = 10017

# Pattern ID to human-readable name mapping
_PATTERN_NAMES: dict[int, str] = {
    UIA_INVOKE_PATTERN_ID: "InvokePattern",
    UIA_VALUE_PATTERN_ID: "ValuePattern",
    UIA_SCROLL_PATTERN_ID: "ScrollPattern",
    UIA_EXPAND_COLLAPSE_PATTERN_ID: "ExpandCollapsePattern",
    UIA_SELECTION_ITEM_PATTERN_ID: "SelectionItemPattern",
    UIA_TOGGLE_PATTERN_ID: "TogglePattern",
}

# Lazy-loaded comtypes pattern interface mapping for QueryInterface.
# GetCurrentPattern() returns POINTER(IUnknown); we must QI to the typed
# interface to access pattern-specific methods (SetValue, Invoke, etc.).
_PATTERN_INTERFACES: dict[int, Any] | None = None


def _get_pattern_interface(pattern_id: int) -> Any | None:
    """Return the comtypes interface class for a given UIA pattern ID."""
    global _PATTERN_INTERFACES
    if _PATTERN_INTERFACES is not None:
        return _PATTERN_INTERFACES.get(pattern_id)
    try:
        from comtypes.gen.UIAutomationClient import (
            IUIAutomationInvokePattern,
            IUIAutomationValuePattern,
            IUIAutomationScrollPattern,
            IUIAutomationExpandCollapsePattern,
            IUIAutomationSelectionItemPattern,
            IUIAutomationTogglePattern,
        )
        _PATTERN_INTERFACES = {
            UIA_INVOKE_PATTERN_ID: IUIAutomationInvokePattern,
            UIA_VALUE_PATTERN_ID: IUIAutomationValuePattern,
            UIA_SCROLL_PATTERN_ID: IUIAutomationScrollPattern,
            UIA_EXPAND_COLLAPSE_PATTERN_ID: IUIAutomationExpandCollapsePattern,
            UIA_SELECTION_ITEM_PATTERN_ID: IUIAutomationSelectionItemPattern,
            UIA_TOGGLE_PATTERN_ID: IUIAutomationTogglePattern,
        }
        return _PATTERN_INTERFACES.get(pattern_id)
    except ImportError:
        _PATTERN_INTERFACES = {}
        return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _get_element_name(element: Any) -> str:
    """Safely get the element's CurrentName."""
    try:
        return element.CurrentName or ""
    except Exception:
        return ""


def _check_enabled(element: Any) -> None:
    """Raise ElementDisabledError if element is not enabled."""
    try:
        if not element.CurrentIsEnabled:
            raise ElementDisabledError(_get_element_name(element))
    except ElementDisabledError:
        raise
    except Exception:
        pass  # If we can't read IsEnabled, proceed optimistically


def _check_onscreen(element: Any) -> None:
    """Check BoundingRectangle; attempt ScrollIntoView if offscreen/empty.

    Raises ElementOffscreenError if the element remains offscreen after
    the scroll attempt.
    """
    name = _get_element_name(element)

    def _rect_is_empty(rect: Any) -> bool:
        try:
            w = int(rect.right - rect.left)
            h = int(rect.bottom - rect.top)
            return w <= 0 or h <= 0
        except Exception:
            return True

    try:
        rect = element.CurrentBoundingRectangle
        if not _rect_is_empty(rect):
            return
    except Exception:
        pass

    # Attempt ScrollItemPattern.ScrollIntoView()
    try:
        scroll_item = element.GetCurrentPattern(_UIA_SCROLL_ITEM_PATTERN_ID)
        if scroll_item:  # truthiness check for null COM pointers
            scroll_item.ScrollIntoView()
            # Re-check
            try:
                rect = element.CurrentBoundingRectangle
                if not _rect_is_empty(rect):
                    return
            except Exception:
                pass
    except Exception:
        pass

    raise ElementOffscreenError(name)


def _get_pattern(element: Any, pattern_id: int) -> Any:
    """Acquire a typed pattern interface or raise PatternNotSupportedError.

    GetCurrentPattern() returns a raw POINTER(IUnknown).  We QueryInterface
    it to the specific comtypes interface (e.g. IUIAutomationValuePattern)
    so that pattern methods like SetValue / Invoke are accessible.
    """
    name = _get_element_name(element)
    pattern_name = _PATTERN_NAMES.get(pattern_id, f"Pattern({pattern_id})")
    try:
        pattern = element.GetCurrentPattern(pattern_id)
    except Exception:
        raise PatternNotSupportedError(pattern_name, name)
    # comtypes may return POINTER(IUnknown) with ptr=0x0 instead of None;
    # use truthiness check (POINTER.__bool__ checks for null pointer).
    if not pattern:
        raise PatternNotSupportedError(pattern_name, name)

    # Cast raw IUnknown to the typed pattern interface.
    # Only QI actual COM POINTER(IUnknown) objects — not mocks or
    # already-typed pointers (which would lose the correct vtable).
    iface = _get_pattern_interface(pattern_id)
    if iface is not None and "IUnknown" in type(pattern).__name__:
        try:
            pattern = pattern.QueryInterface(iface)
        except Exception:
            logger.debug("QueryInterface to %s failed, using raw pointer", pattern_name)
    return pattern


# ------------------------------------------------------------------
# Public pattern wrappers
# ------------------------------------------------------------------

def invoke(element: Any) -> None:
    """InvokePattern.Invoke() — e.g. click a button."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_INVOKE_PATTERN_ID)
    pattern.Invoke()


def set_value(element: Any, text: str) -> None:
    """ValuePattern.SetValue(text)."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_VALUE_PATTERN_ID)
    pattern.SetValue(text)


def get_value(element: Any) -> str | None:
    """ValuePattern.CurrentValue."""
    _check_enabled(element)
    pattern = _get_pattern(element, UIA_VALUE_PATTERN_ID)
    return pattern.CurrentValue


def toggle(element: Any) -> int:
    """TogglePattern.Toggle(), returns new CurrentToggleState."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_TOGGLE_PATTERN_ID)
    pattern.Toggle()
    return pattern.CurrentToggleState


def get_toggle_state(element: Any) -> int | None:
    """TogglePattern.CurrentToggleState."""
    pattern = _get_pattern(element, UIA_TOGGLE_PATTERN_ID)
    return pattern.CurrentToggleState


def expand(element: Any) -> None:
    """ExpandCollapsePattern.Expand()."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_EXPAND_COLLAPSE_PATTERN_ID)
    pattern.Expand()


def collapse(element: Any) -> None:
    """ExpandCollapsePattern.Collapse()."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_EXPAND_COLLAPSE_PATTERN_ID)
    pattern.Collapse()


def get_expand_state(element: Any) -> int | None:
    """ExpandCollapsePattern.CurrentExpandCollapseState."""
    pattern = _get_pattern(element, UIA_EXPAND_COLLAPSE_PATTERN_ID)
    return pattern.CurrentExpandCollapseState


def select(element: Any) -> None:
    """SelectionItemPattern.Select()."""
    _check_enabled(element)
    _check_onscreen(element)
    pattern = _get_pattern(element, UIA_SELECTION_ITEM_PATTERN_ID)
    pattern.Select()


def is_selected(element: Any) -> bool | None:
    """SelectionItemPattern.CurrentIsSelected."""
    pattern = _get_pattern(element, UIA_SELECTION_ITEM_PATTERN_ID)
    return bool(pattern.CurrentIsSelected)


def scroll(element: Any, direction: str, amount: str) -> None:
    """ScrollPattern.Scroll(horizontal_amount, vertical_amount).

    direction: "up", "down", "left", "right"
    amount: "small" or "large"
    """
    _check_enabled(element)

    # ScrollAmount enum: LargeDecrement=0, SmallDecrement=1, NoAmount=2,
    # LargeIncrement=3, SmallIncrement=4
    _NO_AMOUNT = 2
    _amount_map = {
        ("up", "large"): (_NO_AMOUNT, 0),     # vertical LargeDecrement
        ("up", "small"): (_NO_AMOUNT, 1),     # vertical SmallDecrement
        ("down", "large"): (_NO_AMOUNT, 3),   # vertical LargeIncrement
        ("down", "small"): (_NO_AMOUNT, 4),   # vertical SmallIncrement
        ("left", "large"): (0, _NO_AMOUNT),   # horizontal LargeDecrement
        ("left", "small"): (1, _NO_AMOUNT),   # horizontal SmallDecrement
        ("right", "large"): (3, _NO_AMOUNT),  # horizontal LargeIncrement
        ("right", "small"): (4, _NO_AMOUNT),  # horizontal SmallIncrement
    }

    key = (direction.lower(), amount.lower())
    h_amount, v_amount = _amount_map.get(key, (_NO_AMOUNT, _NO_AMOUNT))

    pattern = _get_pattern(element, UIA_SCROLL_PATTERN_ID)
    pattern.Scroll(h_amount, v_amount)


def get_scroll_percent(element: Any) -> tuple[float, float] | None:
    """Return (horizontal_percent, vertical_percent) from ScrollPattern."""
    pattern = _get_pattern(element, UIA_SCROLL_PATTERN_ID)
    h = pattern.CurrentHorizontalScrollPercent
    v = pattern.CurrentVerticalScrollPercent
    return (float(h), float(v))


def get_supported_patterns(element: Any) -> list[str]:
    """Check which of the 6 supported patterns are available on the element.

    Skips ScrollPattern, ExpandCollapsePattern, SelectionItemPattern, and
    TogglePattern probing on Document controls (type 50030) because Win11
    Notepad WinUI3 crashes with a segfault on GetCurrentPattern for these.
    Only probes InvokePattern and ValuePattern on Document controls.
    """
    supported: list[str] = []

    # Determine control type to skip dangerous probes
    skip_patterns: set[int] = set()
    try:
        ct = element.CurrentControlType
        if ct == 50030:  # Document
            # Win11 Notepad WinUI3 Document crashes on these pattern probes
            skip_patterns = {
                UIA_SCROLL_PATTERN_ID,
                UIA_EXPAND_COLLAPSE_PATTERN_ID,
                UIA_SELECTION_ITEM_PATTERN_ID,
                UIA_TOGGLE_PATTERN_ID,
            }
    except Exception:
        pass

    for pattern_id, name in _PATTERN_NAMES.items():
        if pattern_id in skip_patterns:
            continue
        try:
            pat = element.GetCurrentPattern(pattern_id)
            if pat:  # truthiness check — POINTER.__bool__ detects null ptrs
                supported.append(name)
        except Exception:
            pass
    return supported
