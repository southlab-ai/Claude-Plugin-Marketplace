"""Unit tests for src/tools/action.py — cv_action MCP tool with smart routing."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.errors import AccessDeniedError, RateLimitedError
from src.models import ActionResult, FallbackStep, VerificationResult


HWND = 12345


class TestSecurityGate:
    """Tests for the security gate at the top of cv_action."""

    @patch("src.tools.action.validate_hwnd_range", side_effect=ValueError("Invalid HWND"))
    def test_invalid_hwnd_range(self, mock_validate):
        from src.tools.action import cv_action

        result = cv_action(hwnd=0, target="ref_1", action="invoke")
        assert result["success"] is False
        assert "Invalid HWND" in result["error"]["message"]

    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=False)
    @patch("src.tools.action.validate_hwnd_range")
    def test_stale_hwnd(self, mock_range, mock_fresh, mock_restricted, mock_rate, mock_proc):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is False
        assert "no longer valid" in result["error"]["message"]

    @patch("src.tools.action._get_hwnd_process_name", return_value="keepass")
    @patch("src.tools.action.check_restricted", side_effect=AccessDeniedError("keepass"))
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_restricted_process(self, mock_range, mock_fresh, mock_restricted, mock_proc):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is False

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.check_rate_limit", side_effect=RateLimitedError())
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_rate_limited(self, mock_range, mock_fresh, mock_restricted, mock_rate, mock_proc, mock_log):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is False

    @patch("src.tools.action.guard_dry_run", return_value={"success": False, "error": {"code": "DRY_RUN", "message": "dry"}})
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_dry_run(self, mock_range, mock_fresh, mock_restricted, mock_rate, mock_proc, mock_dry):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is False
        assert result["error"]["code"] == "DRY_RUN"


class TestActionValidation:
    """Tests for action parameter validation."""

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_unknown_action(self, mock_range, mock_fresh, mock_restricted, mock_rate, mock_dry, mock_proc, mock_log):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="fly")
        assert result["success"] is False
        assert "Unknown action" in result["error"]["message"]

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_set_value_without_value(self, mock_range, mock_fresh, mock_restricted, mock_rate, mock_dry, mock_proc, mock_log):
        from src.tools.action import cv_action

        result = cv_action(hwnd=HWND, target="ref_1", action="set_value")
        assert result["success"] is False
        assert "requires a 'value'" in result["error"]["message"]


class TestFallbackChain:
    """Tests for the multi-layer fallback chain."""

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value=None)
    @patch("src.tools.action._build_window_state", return_value=None)
    @patch("src.tools.action._run_verification", return_value=VerificationResult(method="uia_state_check", passed=True))
    @patch("src.tools.action._try_uia_pattern", return_value=True)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_layer1_success(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_verify, mock_ws, mock_ss, mock_log,
    ):
        """UIA pattern succeeds at Layer 1."""
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK", "ref_id": "ref_1"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is True
        assert result["layer"] == 1
        assert result["strategy_used"] == "uia_invoke"

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value=None)
    @patch("src.tools.action._build_window_state", return_value=None)
    @patch("src.tools.action._run_verification", return_value=VerificationResult(method="uia_state_check", passed=True))
    @patch("src.tools.action._try_bbox_click", return_value=True)
    @patch("src.tools.action._try_uia_pattern", return_value=False)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_layer2_fallback(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_bbox, mock_verify, mock_ws, mock_ss, mock_log,
    ):
        """UIA pattern fails, falls back to BBox click at Layer 2."""
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK", "ref_id": "ref_1"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is True
        assert result["layer"] == 2
        assert result["strategy_used"] == "uia_bbox_click"

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value=None)
    @patch("src.tools.action._build_window_state", return_value=None)
    @patch("src.tools.action._try_ocr_fallback", return_value=True)
    @patch("src.tools.action._try_bbox_click", return_value=False)
    @patch("src.tools.action._try_uia_pattern", return_value=False)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_layer3_fallback(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_bbox, mock_ocr, mock_ws, mock_ss, mock_log,
    ):
        """All UIA layers fail, falls back to OCR at Layer 3."""
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK", "ref_id": "ref_1"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is True
        assert result["layer"] == 3
        assert result["strategy_used"] == "ocr_sendinput"

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._try_ocr_fallback", return_value=False)
    @patch("src.tools.action._try_bbox_click", return_value=False)
    @patch("src.tools.action._try_uia_pattern", return_value=False)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_all_layers_fail(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_bbox, mock_ocr, mock_log,
    ):
        """All layers fail -> error response with fallback chain."""
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK", "ref_id": "ref_1"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is False
        assert "fallback_chain" in result


class TestTimeoutBudget:
    """Tests for timeout budget management."""

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._try_ocr_fallback", return_value=False)
    @patch("src.tools.action._try_bbox_click", return_value=False)
    @patch("src.tools.action._try_uia_pattern", return_value=False)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_timing_ms_in_response(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_bbox, mock_ocr, mock_log,
    ):
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke", action_timeout_ms=5000)
        assert "timing_ms" in result


class TestResponseFormat:
    """Tests for the shape of cv_action responses."""

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value="/tmp/ss.png")
    @patch("src.tools.action._build_window_state", return_value={"hwnd": HWND, "title": "Test"})
    @patch("src.tools.action._run_verification", return_value=VerificationResult(method="uia_state_check", passed=True))
    @patch("src.tools.action._try_uia_pattern", return_value=True)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_success_response_shape(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_verify, mock_ws, mock_ss, mock_log,
    ):
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke")
        assert result["success"] is True
        assert "strategy_used" in result
        assert "layer" in result
        assert "verification" in result
        assert "timing_ms" in result
        assert "fallback_chain" in result
        assert result["image_path"] == "/tmp/ss.png"
        assert result["window_state"]["hwnd"] == HWND

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value=None)
    @patch("src.tools.action._build_window_state", return_value=None)
    @patch("src.tools.action._run_verification", return_value=VerificationResult(method="uia_state_check", passed=True))
    @patch("src.tools.action._try_uia_pattern", return_value=True)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_no_screenshot_when_disabled(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_verify, mock_ws, mock_ss, mock_log,
    ):
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="invoke", screenshot=False)
        assert result["success"] is True
        # Screenshot should not be captured
        mock_ss.assert_not_called()


class TestActionAliases:
    """Tests for action name aliasing."""

    @patch("src.tools.action.log_action")
    @patch("src.tools.action._capture_post_action", return_value=None)
    @patch("src.tools.action._build_window_state", return_value=None)
    @patch("src.tools.action._run_verification", return_value=VerificationResult(method="uia_state_check", passed=True))
    @patch("src.tools.action._try_uia_pattern", return_value=True)
    @patch("src.tools.action._capture_pre_state", return_value=True)
    @patch("src.tools.action._resolve_element")
    @patch("src.tools.action._try_adapter_layer", return_value=None)
    @patch("src.tools.action._get_hwnd_process_name", return_value="notepad")
    @patch("src.tools.action.guard_dry_run", return_value=None)
    @patch("src.tools.action.check_rate_limit")
    @patch("src.tools.action.check_restricted")
    @patch("src.tools.action.validate_hwnd_fresh", return_value=True)
    @patch("src.tools.action.validate_hwnd_range")
    def test_click_alias_maps_to_invoke(
        self, mock_range, mock_fresh, mock_restricted, mock_rate,
        mock_dry, mock_proc, mock_adapter, mock_resolve, mock_pre,
        mock_uia, mock_verify, mock_ws, mock_ss, mock_log,
    ):
        from src.tools.action import cv_action

        mock_resolve.return_value = ({"name": "OK"}, MagicMock())

        result = cv_action(hwnd=HWND, target="ref_1", action="click")
        assert result["success"] is True
        assert result["strategy_used"] == "uia_invoke"


class TestHelpers:
    """Tests for internal helper functions."""

    def test_check_deadline_within(self):
        from src.tools.action import _check_deadline
        # Deadline in the future
        assert _check_deadline(time.monotonic() + 10) is True

    def test_check_deadline_expired(self):
        from src.tools.action import _check_deadline
        # Deadline in the past
        assert _check_deadline(time.monotonic() - 1) is False

    def test_elapsed_ms(self):
        from src.tools.action import _elapsed_ms
        start = time.monotonic()
        # Should be very small
        elapsed = _elapsed_ms(start)
        assert elapsed >= 0
        assert elapsed < 1000  # less than 1 second

    def test_action_aliases(self):
        from src.tools.action import _ACTION_ALIASES
        assert _ACTION_ALIASES["click"] == "invoke"
        assert _ACTION_ALIASES["type"] == "set_value"


class TestResolveElement:
    """Tests for _resolve_element with mocked imports."""

    def test_resolve_element_import_error(self):
        """When element_cache/target_resolver not available, returns (None, None)."""
        from src.tools.action import _resolve_element

        with patch.dict("sys.modules", {"src.utils.element_cache": None, "src.utils.target_resolver": None}):
            meta, com = _resolve_element(HWND, "ref_1")
            # Should gracefully return None when modules not available
            assert meta is None
            assert com is None


class TestTryUiaPattern:
    """Tests for _try_uia_pattern."""

    def test_uia_pattern_records_fallback_step(self):
        """Pattern invocation records a FallbackStep."""
        from src.tools.action import _try_uia_pattern

        fallback_chain = []
        com_el = MagicMock()

        mock_patterns = MagicMock()
        mock_patterns.invoke.return_value = None
        with patch.dict("sys.modules", {"src.utils.uia_patterns": mock_patterns}):
            result = _try_uia_pattern("invoke", com_el, None, HWND, fallback_chain)

        assert result is True
        assert len(fallback_chain) == 1
        assert fallback_chain[0].strategy == "uia_invoke"
        assert fallback_chain[0].result == "success"

    def test_uia_pattern_failure_records_step(self):
        """Failed pattern invocation records error in fallback chain."""
        from src.tools.action import _try_uia_pattern

        fallback_chain = []
        com_el = MagicMock()

        mock_patterns = MagicMock()
        mock_patterns.invoke.side_effect = Exception("Pattern not supported")

        import src.utils as utils_pkg
        with patch.object(utils_pkg, "uia_patterns", mock_patterns):
            result = _try_uia_pattern("invoke", com_el, None, HWND, fallback_chain)

        assert result is False
        assert len(fallback_chain) == 1
        assert "pattern_not_supported" in fallback_chain[0].result
