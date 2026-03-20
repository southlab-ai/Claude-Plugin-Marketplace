"""UI Automation utilities — flat element search and programmatic invocation.

Uses FindAll(TreeScope_Descendants) for fast, depth-unlimited element discovery
and UIA patterns (Toggle, Invoke, LegacyIAccessible) to activate controls that
don't respond to SendInput (e.g. WinUI 3 toolbar buttons).
"""

from __future__ import annotations

import logging
from typing import Any

import comtypes
import comtypes.client

logger = logging.getLogger(__name__)

# UIA pattern IDs
_PATTERN_INVOKE = 10000
_PATTERN_SELECTION_ITEM = 10010
_PATTERN_TOGGLE = 10015
_PATTERN_LEGACY = 10018

# TreeScope
_TREESCOPE_DESCENDANTS = 4

# UIA property IDs
_UIA_NAME = 30005
_UIA_CONTROL_TYPE = 30003
_UIA_AUTOMATION_ID = 30011

# Control type names
CONTROL_TYPE_NAMES: dict[int, str] = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox",
    50003: "ComboBox", 50004: "Edit", 50005: "Hyperlink",
    50006: "Image", 50007: "ListItem", 50008: "List",
    50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar",
    50018: "Tab", 50019: "TabItem", 50020: "Text",
    50021: "ToolBar", 50022: "ToolTip", 50023: "Tree",
    50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem",
    50030: "Document", 50031: "SplitButton", 50032: "Window",
    50033: "Pane", 50034: "Header", 50035: "HeaderItem",
    50036: "Table", 50037: "TitleBar", 50038: "Separator",
}


def _get_uia() -> Any:
    """Get or create the IUIAutomation COM instance."""
    from src.utils.uia import _safe_init_uia
    return _safe_init_uia()


def find_all_elements(hwnd: int) -> list[dict]:
    """Find ALL UI elements in a window using FindAll (flat, no depth limit).

    Returns a list of dicts with: name, control_type, control_type_id,
    rect {x, y, width, height}, automation_id, and the raw COM element.
    """
    uia = _get_uia()
    root = uia.ElementFromHandle(hwnd)
    true_cond = uia.CreateTrueCondition()
    all_els = root.FindAll(_TREESCOPE_DESCENDANTS, true_cond)

    results: list[dict] = []
    count = all_els.Length

    for i in range(count):
        el = all_els.GetElement(i)
        try:
            name = el.CurrentName or ""
            ctrl_type_id = el.CurrentControlType
            rect = el.CurrentBoundingRectangle
            auto_id = ""
            try:
                auto_id = el.CurrentAutomationId or ""
            except Exception:
                pass

            results.append({
                "name": name,
                "control_type": CONTROL_TYPE_NAMES.get(ctrl_type_id, f"Unknown({ctrl_type_id})"),
                "control_type_id": ctrl_type_id,
                "rect": {
                    "x": int(rect.left),
                    "y": int(rect.top),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                },
                "automation_id": auto_id,
                "_element": el,  # raw COM element for invocation
            })
        except Exception:
            continue

    return results


def find_element_by_name(
    hwnd: int,
    name: str,
    control_type_id: int | None = None,
) -> Any | None:
    """Find a single UI element by name (and optionally control type).

    Returns the raw IUIAutomationElement or None.
    """
    uia = _get_uia()
    root = uia.ElementFromHandle(hwnd)

    name_cond = uia.CreatePropertyCondition(_UIA_NAME, name)
    if control_type_id is not None:
        type_cond = uia.CreatePropertyCondition(_UIA_CONTROL_TYPE, control_type_id)
        cond = uia.CreateAndCondition(name_cond, type_cond)
    else:
        cond = name_cond

    return root.FindFirst(_TREESCOPE_DESCENDANTS, cond)


def invoke_element(element: Any) -> tuple[bool, str]:
    """Invoke a UI element using the best available UIA pattern.

    Tries in order: InvokePattern, TogglePattern, SelectionItemPattern,
    LegacyIAccessible.DoDefaultAction.

    Returns (success, method_used).
    """
    # 1. Try InvokePattern
    try:
        pattern = element.GetCurrentPattern(_PATTERN_INVOKE)
        if pattern:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import IUIAutomationInvokePattern
            invoke = pattern.QueryInterface(IUIAutomationInvokePattern)
            invoke.Invoke()
            return True, "InvokePattern"
    except Exception:
        pass

    # 2. Try TogglePattern
    try:
        pattern = element.GetCurrentPattern(_PATTERN_TOGGLE)
        if pattern:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import IUIAutomationTogglePattern
            toggle = pattern.QueryInterface(IUIAutomationTogglePattern)
            toggle.Toggle()
            return True, "TogglePattern"
    except Exception:
        pass

    # 3. Try SelectionItemPattern
    try:
        pattern = element.GetCurrentPattern(_PATTERN_SELECTION_ITEM)
        if pattern:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import IUIAutomationSelectionItemPattern
            sel = pattern.QueryInterface(IUIAutomationSelectionItemPattern)
            sel.Select()
            return True, "SelectionItemPattern"
    except Exception:
        pass

    # 4. Try LegacyIAccessible.DoDefaultAction
    try:
        pattern = element.GetCurrentPattern(_PATTERN_LEGACY)
        if pattern:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import IUIAutomationLegacyIAccessiblePattern
            legacy = pattern.QueryInterface(IUIAutomationLegacyIAccessiblePattern)
            legacy.DoDefaultAction()
            return True, "LegacyIAccessible"
    except Exception:
        pass

    return False, "none"


def click_ui_element(
    hwnd: int,
    name: str,
    control_type_id: int | None = None,
) -> tuple[bool, str]:
    """Find a UI element by name and invoke it via UIA patterns.

    This bypasses SendInput entirely — it calls the control's action handler
    directly through UI Automation, which works on WinUI 3, UWP, WPF, and
    Win32 apps.

    Args:
        hwnd: Window handle to search in.
        name: Element name to find (exact match).
        control_type_id: Optional control type filter (e.g. 50000 for Button).

    Returns:
        (success, method_or_error) tuple.
    """
    try:
        element = find_element_by_name(hwnd, name, control_type_id)
        if element is None:
            return False, f"Element '{name}' not found"

        return invoke_element(element)
    except Exception as e:
        return False, f"Error: {e}"
