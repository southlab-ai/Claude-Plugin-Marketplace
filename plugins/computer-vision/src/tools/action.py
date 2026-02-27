"""MCP tool for smart action routing: cv_action with multi-layer fallback.

Layer 0: Adapter registry (e.g., CDP for browsers)
Layer 1: UIA Pattern invocation (Invoke, SetValue, Toggle, etc.)
Layer 2: UIA BBox + Click (get bounding rect, click center)
Layer 3: OCR + SendInput fallback (find text, click)

Each layer is tried in order. The first success wins. A fallback_chain
records every step attempted for transparency.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.server import mcp
from src import config
from src.errors import (
    make_error,
    make_success,
    INVALID_INPUT,
    INPUT_FAILED,
    TIMEOUT,
    UIA_ERROR,
)
from src.models import ActionResult, FallbackStep, VerificationResult
from src.utils.security import (
    validate_hwnd_range,
    validate_hwnd_fresh,
    check_restricted,
    check_rate_limit,
    guard_dry_run,
    log_action,
)
from src.utils.action_helpers import (
    _capture_post_action,
    _build_window_state,
    _get_hwnd_process_name,
)

logger = logging.getLogger(__name__)

# Action types that map to UIA patterns
_PATTERN_ACTIONS = frozenset({
    "invoke", "click",
    "set_value", "type",
    "toggle",
    "expand",
    "collapse",
    "select",
    "scroll",
    "get_value",
    "get_text",
})

# Map user-facing action names to canonical internal names
_ACTION_ALIASES = {
    "click": "invoke",
    "type": "set_value",
}


@mcp.tool()
def cv_action(
    hwnd: int,
    target: str,
    action: str,
    value: str | None = None,
    action_timeout_ms: int = 5000,
    screenshot: bool = True,
) -> dict:
    """Perform a smart UI action on an element with automatic fallback.

    Resolves the target element, then attempts the action through multiple
    strategies (UIA patterns -> BBox click -> OCR fallback), recording each
    step in the fallback chain.

    Args:
        hwnd: Window handle of the target application.
        target: Element identifier — ref_id (e.g., "ref_5") or text label.
        action: Action to perform: "invoke", "click", "set_value", "type",
                "toggle", "expand", "collapse", "select", "scroll".
        value: Value for set_value/type actions, or scroll direction ("up"/"down"/"left"/"right").
        action_timeout_ms: Total timeout budget in milliseconds (default 5000).
        screenshot: Whether to capture a post-action screenshot (default True).
    """
    start_time = time.monotonic()
    fallback_chain: list[FallbackStep] = []

    try:
        # --- Security gate ---
        validate_hwnd_range(hwnd)
        if not validate_hwnd_fresh(hwnd):
            return make_error(INVALID_INPUT, f"HWND {hwnd} is no longer valid.")

        process_name = _get_hwnd_process_name(hwnd)
        if process_name:
            check_restricted(process_name)

        check_rate_limit()

        params = {
            "hwnd": hwnd, "target": target, "action": action,
        }
        if value is not None:
            params["value"] = value

        dry = guard_dry_run("cv_action", params)
        if dry is not None:
            return dry

        # --- Normalize action ---
        canonical_action = _ACTION_ALIASES.get(action, action)
        if canonical_action not in _PATTERN_ACTIONS:
            return make_error(INVALID_INPUT, f"Unknown action: {action!r}")

        # Validate value for set_value
        if canonical_action == "set_value" and value is None:
            return make_error(INVALID_INPUT, "Action 'set_value' requires a 'value' parameter.")

        deadline = start_time + (action_timeout_ms / 1000.0)

        # --- Layer 0: Adapter registry ---
        layer0_result = _try_adapter_layer(
            hwnd, target, canonical_action, value, fallback_chain, deadline
        )
        if layer0_result is not None:
            return _finalize_result(
                layer0_result, fallback_chain, hwnd, screenshot, start_time, layer=0
            )

        # --- Resolve target element ---
        element_meta, com_element = _resolve_element(hwnd, target)
        if element_meta is None or com_element is None:
            # If target resolution fails, fall through to Layer 3 (OCR)
            fallback_chain.append(FallbackStep(
                strategy="uia_resolve",
                result="element_not_found",
                duration_ms=_elapsed_ms(start_time),
            ))
        else:
            # --- Capture pre-state for verification ---
            pre_state = _capture_pre_state(canonical_action, com_element, value)

            # --- Layer 1: UIA Pattern invocation ---
            if _check_deadline(deadline):
                layer1_start = time.monotonic()
                layer1_ok = _try_uia_pattern(
                    canonical_action, com_element, value, hwnd, fallback_chain
                )
                if layer1_ok:
                    verification = _run_verification(
                        canonical_action, element_meta, pre_state, hwnd, com_element
                    )
                    result = ActionResult(
                        success=True,
                        strategy_used=f"uia_{canonical_action}",
                        layer=1,
                        verification=verification,
                        element=element_meta,
                        fallback_chain=fallback_chain,
                    )
                    return _finalize_result(
                        result, fallback_chain, hwnd, screenshot, start_time, layer=1
                    )

            # --- Layer 2: UIA BBox + Click ---
            if _check_deadline(deadline) and canonical_action in ("invoke", "set_value"):
                layer2_start = time.monotonic()
                layer2_ok = _try_bbox_click(
                    com_element, element_meta, canonical_action, value, hwnd, fallback_chain
                )
                if layer2_ok:
                    verification = _run_verification(
                        canonical_action, element_meta, pre_state, hwnd, com_element
                    )
                    result = ActionResult(
                        success=True,
                        strategy_used="uia_bbox_click",
                        layer=2,
                        verification=verification,
                        element=element_meta,
                        fallback_chain=fallback_chain,
                    )
                    return _finalize_result(
                        result, fallback_chain, hwnd, screenshot, start_time, layer=2
                    )

        # --- Layer 3: OCR + SendInput fallback ---
        if _check_deadline(deadline):
            layer3_start = time.monotonic()
            layer3_ok = _try_ocr_fallback(
                hwnd, target, canonical_action, value, fallback_chain
            )
            if layer3_ok:
                result = ActionResult(
                    success=True,
                    strategy_used="ocr_sendinput",
                    layer=3,
                    verification=VerificationResult(
                        method="none", passed=False, detail="OCR fallback, no UIA verification"
                    ),
                    fallback_chain=fallback_chain,
                )
                return _finalize_result(
                    result, fallback_chain, hwnd, screenshot, start_time, layer=3
                )

        # All layers exhausted
        elapsed = _elapsed_ms(start_time)
        if not _check_deadline(deadline):
            return _make_action_error(
                TIMEOUT,
                f"Action timed out after {elapsed:.0f}ms",
                fallback_chain, hwnd, start_time,
            )

        return _make_action_error(
            INPUT_FAILED,
            f"All action layers failed for target={target!r} action={action!r}",
            fallback_chain, hwnd, start_time,
        )

    except Exception as exc:
        log_action("cv_action", {"hwnd": hwnd, "target": target, "action": action}, "error")
        elapsed = _elapsed_ms(start_time)
        error_result = make_error(INPUT_FAILED, str(exc))
        error_result["fallback_chain"] = [s.model_dump() for s in fallback_chain]
        error_result["timing_ms"] = elapsed
        return error_result


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------


def _try_adapter_layer(
    hwnd: int,
    target: str,
    action: str,
    value: str | None,
    fallback_chain: list[FallbackStep],
    deadline: float,
) -> ActionResult | None:
    """Layer 0: Try adapter registry (CDP, etc.)."""
    try:
        from src.adapters import get_adapter
        adapter = get_adapter(hwnd)
        if adapter is not None:
            adapter_name = type(adapter).__name__.lower().replace("adapter", "")
            if not adapter.supports_action(action):
                fallback_chain.append(FallbackStep(
                    strategy=f"adapter_{adapter_name}",
                    result="action_not_supported",
                    duration_ms=0,
                ))
                return None
            start = time.monotonic()
            result = adapter.execute(hwnd, target, action, value)
            duration = (time.monotonic() - start) * 1000
            if result.success:
                fallback_chain.append(FallbackStep(
                    strategy=f"adapter_{adapter_name}",
                    result="success",
                    duration_ms=duration,
                ))
                result.fallback_chain = fallback_chain
                return result
            else:
                fallback_chain.append(FallbackStep(
                    strategy=f"adapter_{adapter_name}",
                    result="adapter_failed",
                    duration_ms=duration,
                ))
    except ImportError:
        pass  # Adapters module not ready yet
    except Exception as exc:
        fallback_chain.append(FallbackStep(
            strategy="adapter",
            result=f"error: {exc}",
            duration_ms=0,
        ))
    return None


def _resolve_element(hwnd: int, target: str) -> tuple[dict | None, Any]:
    """Resolve target to (element_meta dict, COM element)."""
    try:
        from src.utils.element_cache import get_element_cache
        from src.utils.target_resolver import resolve_target

        cache = get_element_cache()
        element_meta, com_element = resolve_target(hwnd, target, cache)
        return element_meta, com_element
    except ImportError:
        logger.debug("target_resolver or element_cache not available yet")
        return None, None
    except Exception as exc:
        logger.debug("Target resolution failed: %s", exc)
        return None, None


def _capture_pre_state(action: str, com_element: Any, value: str | None) -> Any:
    """Capture pre-action state for verification."""
    try:
        if action == "invoke":
            return bool(com_element.CurrentIsEnabled)

        if action == "set_value":
            # For set_value verification, pre_state is the expected value
            return value

        if action == "toggle":
            from src.utils.uia_patterns import get_toggle_state
            return get_toggle_state(com_element)

        if action in ("expand", "collapse"):
            from src.utils.uia_patterns import get_expand_state
            return get_expand_state(com_element)

        if action == "select":
            from src.utils.uia_patterns import is_selected
            return is_selected(com_element)

        if action == "scroll":
            from src.utils.uia_patterns import get_scroll_percent
            return get_scroll_percent(com_element)

    except Exception as exc:
        logger.debug("Failed to capture pre-state for %s: %s", action, exc)
    return None


def _try_uia_pattern(
    action: str,
    com_element: Any,
    value: str | None,
    hwnd: int,
    fallback_chain: list[FallbackStep],
) -> bool:
    """Layer 1: Try UIA pattern invocation."""
    start = time.monotonic()
    try:
        from src.utils import uia_patterns

        if action == "invoke":
            uia_patterns.invoke(com_element)
        elif action == "set_value":
            # Check if text is long enough to use clipboard
            if value and len(value) > config.CLIPBOARD_THRESHOLD:
                from src.utils.clipboard import paste_text
                ok = paste_text(value, hwnd, com_element=com_element)
                if not ok:
                    raise RuntimeError("Clipboard paste failed")
            else:
                uia_patterns.set_value(com_element, value or "")
        elif action == "toggle":
            uia_patterns.toggle(com_element)
        elif action == "expand":
            uia_patterns.expand(com_element)
        elif action == "collapse":
            uia_patterns.collapse(com_element)
        elif action == "select":
            uia_patterns.select(com_element)
        elif action == "scroll":
            direction = value or "down"
            uia_patterns.scroll(com_element, direction, 3)
        else:
            raise ValueError(f"Unknown pattern action: {action}")

        duration = (time.monotonic() - start) * 1000
        fallback_chain.append(FallbackStep(
            strategy=f"uia_{action}",
            result="success",
            duration_ms=duration,
        ))
        return True

    except Exception as exc:
        duration = (time.monotonic() - start) * 1000
        result_str = "pattern_not_supported" if "not supported" in str(exc).lower() else str(exc)
        fallback_chain.append(FallbackStep(
            strategy=f"uia_{action}",
            result=result_str,
            duration_ms=duration,
        ))
        logger.debug("UIA pattern %s failed: %s", action, exc)
        return False


def _try_bbox_click(
    com_element: Any,
    element_meta: dict | None,
    action: str,
    value: str | None,
    hwnd: int,
    fallback_chain: list[FallbackStep],
) -> bool:
    """Layer 2: Get element bounding rect and click center."""
    start = time.monotonic()
    try:
        # Get bounding rectangle from COM element
        rect = com_element.CurrentBoundingRectangle
        left, top = int(rect.left), int(rect.top)
        right, bottom = int(rect.right), int(rect.bottom)
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            raise ValueError("Element has empty bounding rectangle")

        center_x = left + width // 2
        center_y = top + height // 2

        # Normalize coordinates for SendInput
        from src.coordinates import normalize_for_sendinput
        norm_x, norm_y = normalize_for_sendinput(center_x, center_y)

        from src.utils.win32_input import send_mouse_click
        ok = send_mouse_click(norm_x, norm_y, "left", "single")
        if not ok:
            raise RuntimeError("SendInput failed for bbox click")

        # For set_value after click, type the text
        if action == "set_value" and value:
            import time as _time
            _time.sleep(0.05)  # Let click register focus
            if len(value) > config.CLIPBOARD_THRESHOLD:
                from src.utils.clipboard import paste_text
                paste_text(value, hwnd, com_element=com_element)
            else:
                from src.utils.win32_input import type_unicode_string
                type_unicode_string(value)

        duration = (time.monotonic() - start) * 1000
        fallback_chain.append(FallbackStep(
            strategy="uia_bbox_click",
            result="success",
            duration_ms=duration,
        ))
        return True

    except Exception as exc:
        duration = (time.monotonic() - start) * 1000
        fallback_chain.append(FallbackStep(
            strategy="uia_bbox_click",
            result=str(exc),
            duration_ms=duration,
        ))
        logger.debug("BBox click failed: %s", exc)
        return False


def _try_ocr_fallback(
    hwnd: int,
    target: str,
    action: str,
    value: str | None,
    fallback_chain: list[FallbackStep],
) -> bool:
    """Layer 3: OCR + SendInput fallback using existing find + click pipeline."""
    start = time.monotonic()
    try:
        # Use existing cv_find pipeline to locate the element by text
        from src.tools.find import _find_matches
        matches = _find_matches(hwnd, target)

        if not matches:
            fallback_chain.append(FallbackStep(
                strategy="ocr_sendinput",
                result="element_not_found",
                duration_ms=(time.monotonic() - start) * 1000,
            ))
            return False

        best = matches[0]
        bbox = best.bbox

        # Click the center of the matched region
        center_x = bbox.x + bbox.width // 2
        center_y = bbox.y + bbox.height // 2

        from src.coordinates import normalize_for_sendinput
        norm_x, norm_y = normalize_for_sendinput(center_x, center_y)

        from src.utils.win32_input import send_mouse_click
        ok = send_mouse_click(norm_x, norm_y, "left", "single")
        if not ok:
            raise RuntimeError("SendInput failed for OCR click")

        # For set_value, type text after clicking
        if action == "set_value" and value:
            time.sleep(0.05)
            if len(value) > config.CLIPBOARD_THRESHOLD:
                from src.utils.clipboard import paste_text
                paste_text(value, hwnd)
            else:
                from src.utils.win32_input import type_unicode_string
                type_unicode_string(value)

        duration = (time.monotonic() - start) * 1000
        fallback_chain.append(FallbackStep(
            strategy="ocr_sendinput",
            result="success",
            duration_ms=duration,
        ))
        return True

    except ImportError:
        fallback_chain.append(FallbackStep(
            strategy="ocr_sendinput",
            result="find module not available",
            duration_ms=(time.monotonic() - start) * 1000,
        ))
        return False
    except Exception as exc:
        duration = (time.monotonic() - start) * 1000
        fallback_chain.append(FallbackStep(
            strategy="ocr_sendinput",
            result=str(exc),
            duration_ms=duration,
        ))
        logger.debug("OCR fallback failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_verification(
    action: str,
    element_meta: dict | None,
    pre_state: Any,
    hwnd: int,
    com_element: Any,
) -> VerificationResult:
    """Run post-action verification."""
    try:
        from src.utils.verification import verify_action
        return verify_action(
            action=action,
            element_meta=element_meta,
            pre_state=pre_state,
            hwnd=hwnd,
            com_element=com_element,
        )
    except Exception as exc:
        return VerificationResult(method="none", passed=False, detail=str(exc))


def _finalize_result(
    result: ActionResult,
    fallback_chain: list[FallbackStep],
    hwnd: int,
    screenshot: bool,
    start_time: float,
    layer: int,
) -> dict:
    """Finalize the ActionResult with timing, screenshot, and window state."""
    elapsed = _elapsed_ms(start_time)
    result.timing_ms = elapsed
    result.layer = layer
    result.fallback_chain = fallback_chain

    # Window state
    window_state = _build_window_state(hwnd)
    if window_state:
        result.window_state = window_state

    # Post-action screenshot
    if screenshot:
        image_path = _capture_post_action(hwnd, delay_ms=150)
        if image_path:
            result.image_path = image_path

    log_action(
        "cv_action",
        {"hwnd": hwnd, "strategy": result.strategy_used, "layer": layer},
        "ok" if result.success else "fail",
    )

    return result.model_dump()


def _make_action_error(
    code: str,
    message: str,
    fallback_chain: list[FallbackStep],
    hwnd: int,
    start_time: float,
) -> dict:
    """Build an error response with fallback chain and timing."""
    elapsed = _elapsed_ms(start_time)
    error = make_error(code, message)
    error["fallback_chain"] = [s.model_dump() for s in fallback_chain]
    error["timing_ms"] = elapsed
    log_action("cv_action", {"hwnd": hwnd}, "fail")
    return error


def _check_deadline(deadline: float) -> bool:
    """Check if we still have time before the deadline."""
    return time.monotonic() < deadline


def _elapsed_ms(start_time: float) -> float:
    """Calculate elapsed time in milliseconds."""
    return (time.monotonic() - start_time) * 1000
