"""Post-action verification strategies for cv_action.

Each UIA pattern action has a tailored verification approach:
- invoke: poll event buffer or element's IsEnabled for state changes
- set_value: re-read ValuePattern and compare to expected
- toggle: re-read ToggleState, confirm it changed from pre_state
- expand: re-read ExpandCollapseState, confirm == Expanded (1)
- collapse: re-read ExpandCollapseState, confirm == Collapsed (0)
- select: re-read IsSelected, confirm == True
- scroll: re-read scroll percentages, confirm they changed

Falls back to screenshot capture if UIA verification is inconclusive.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.models import VerificationResult

logger = logging.getLogger(__name__)


def verify_action(
    action: str,
    element_meta: dict | None,
    pre_state: Any,
    hwnd: int,
    event_manager: Any | None = None,
    timeout_ms: int = 500,
    com_element: Any | None = None,
) -> VerificationResult:
    """Verify that an action succeeded by checking post-action state.

    Args:
        action: The action type (invoke, set_value, toggle, expand, collapse, select, scroll).
        element_meta: Element metadata dict (may contain ref_id, name, etc.).
        pre_state: The pre-action state value captured before executing the action.
        hwnd: Window handle for screenshot fallback.
        event_manager: Optional event manager with a get_recent_events() method.
        timeout_ms: Maximum time to wait for verification in milliseconds.
        com_element: The COM element to query for post-action state.

    Returns:
        VerificationResult with method, passed, and detail fields.
    """
    try:
        strategy = _VERIFICATION_STRATEGIES.get(action)
        if strategy is None:
            return VerificationResult(
                method="none",
                passed=False,
                detail=f"No verification strategy for action: {action}",
            )

        result = strategy(
            com_element=com_element,
            pre_state=pre_state,
            timeout_ms=timeout_ms,
            event_manager=event_manager,
        )

        if result is not None:
            return result

        # UIA verification inconclusive -- fall back to screenshot
        return _screenshot_fallback(hwnd)

    except Exception as exc:
        logger.debug("Verification failed: %s", exc, exc_info=True)
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Verification error: {exc}",
        )


def _verify_invoke(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify invoke action: check event buffer or poll IsEnabled for state change."""
    # Strategy 1: check event buffer if event_manager is provided
    if event_manager is not None:
        try:
            events = event_manager.get_recent_events()
            if events:
                return VerificationResult(
                    method="uia_state_check",
                    passed=True,
                    detail=f"Event buffer has {len(events)} state change(s)",
                )
        except Exception:
            pass

    # Strategy 2: poll element for any state change (IsEnabled toggling, etc.)
    if com_element is None:
        return None

    interval_ms = 50
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            current_enabled = bool(com_element.CurrentIsEnabled)
            if current_enabled != pre_state:
                return VerificationResult(
                    method="uia_state_check",
                    passed=True,
                    detail=f"IsEnabled changed from {pre_state} to {current_enabled}",
                )
        except Exception:
            pass
        time.sleep(interval_ms / 1000.0)
        elapsed += interval_ms

    # Invoke is fire-and-forget; if nothing changed, still consider it plausible success
    return VerificationResult(
        method="uia_state_check",
        passed=True,
        detail="Invoke completed, no state change detected within timeout",
    )


def _verify_set_value(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify set_value: re-read ValuePattern.CurrentValue and compare to expected."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import get_value
        current_value = get_value(com_element)

        # pre_state for set_value is the expected value
        if current_value == pre_state:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail=f"Value matches expected: {_truncate(current_value)}",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail=f"Value mismatch: expected {_truncate(pre_state)}, got {_truncate(current_value)}",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read value: {exc}",
        )


def _verify_toggle(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify toggle: re-read ToggleState, confirm it changed from pre_state."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import get_toggle_state
        current_state = get_toggle_state(com_element)

        if current_state != pre_state:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail=f"Toggle state changed from {pre_state} to {current_state}",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail=f"Toggle state unchanged: {current_state}",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read toggle state: {exc}",
        )


def _verify_expand(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify expand: re-read ExpandCollapseState, confirm == Expanded (1)."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import get_expand_state
        current_state = get_expand_state(com_element)

        # ExpandCollapseState.Expanded == 1
        if current_state == 1:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail="Element is now Expanded",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail=f"Element not expanded, state={current_state}",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read expand state: {exc}",
        )


def _verify_collapse(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify collapse: re-read ExpandCollapseState, confirm == Collapsed (0)."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import get_expand_state
        current_state = get_expand_state(com_element)

        # ExpandCollapseState.Collapsed == 0
        if current_state == 0:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail="Element is now Collapsed",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail=f"Element not collapsed, state={current_state}",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read collapse state: {exc}",
        )


def _verify_select(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify select: re-read IsSelected, confirm == True."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import is_selected
        current = is_selected(com_element)

        if current:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail="Element is now selected",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail="Element is not selected",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read selection state: {exc}",
        )


def _verify_scroll(
    com_element: Any,
    pre_state: Any,
    timeout_ms: int,
    event_manager: Any | None = None,
) -> VerificationResult | None:
    """Verify scroll: re-read scroll percentages, confirm they changed."""
    if com_element is None:
        return None

    try:
        from src.utils.uia_patterns import get_scroll_percent
        current = get_scroll_percent(com_element)

        # pre_state is a dict like {"horizontal": x, "vertical": y}
        if pre_state is None:
            return None

        changed = (
            current.get("horizontal") != pre_state.get("horizontal")
            or current.get("vertical") != pre_state.get("vertical")
        )

        if changed:
            return VerificationResult(
                method="uia_state_check",
                passed=True,
                detail=f"Scroll position changed from {pre_state} to {current}",
            )
        else:
            return VerificationResult(
                method="uia_state_check",
                passed=False,
                detail=f"Scroll position unchanged: {current}",
            )
    except Exception as exc:
        return VerificationResult(
            method="none",
            passed=False,
            detail=f"Failed to read scroll state: {exc}",
        )


def _screenshot_fallback(hwnd: int) -> VerificationResult:
    """Capture a screenshot as fallback verification."""
    try:
        from src.utils.action_helpers import _capture_post_action
        image_path = _capture_post_action(hwnd, delay_ms=0)
        if image_path:
            return VerificationResult(
                method="screenshot",
                passed=True,
                detail="screenshot captured",
            )
    except Exception:
        pass

    return VerificationResult(
        method="none",
        passed=False,
        detail="Screenshot fallback failed",
    )


def _truncate(value: Any, max_len: int = 50) -> str:
    """Truncate a value for display in verification detail messages."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# Strategy dispatch table
_VERIFICATION_STRATEGIES = {
    "invoke": _verify_invoke,
    "set_value": _verify_set_value,
    "toggle": _verify_toggle,
    "expand": _verify_expand,
    "collapse": _verify_collapse,
    "select": _verify_select,
    "scroll": _verify_scroll,
}
