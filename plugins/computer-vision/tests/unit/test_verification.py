"""Unit tests for src/utils/verification.py — per-pattern verification strategies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.models import VerificationResult


HWND = 12345


class TestVerifyInvoke:
    """Tests for invoke verification strategy."""

    @patch("src.utils.verification.time")
    def test_invoke_event_manager_with_events(self, mock_time):
        """Event buffer with events -> success."""
        from src.utils.verification import verify_action

        event_mgr = MagicMock()
        event_mgr.get_recent_events.return_value = [{"type": "state_change"}]
        com_el = MagicMock()

        result = verify_action(
            action="invoke",
            element_meta={"name": "OK"},
            pre_state=True,
            hwnd=HWND,
            event_manager=event_mgr,
            com_element=com_el,
        )

        assert result.method == "uia_state_check"
        assert result.passed is True
        assert "1" in result.detail

    @patch("src.utils.verification.time")
    def test_invoke_state_change_detected(self, mock_time):
        """IsEnabled changes from True to False -> success."""
        from src.utils.verification import verify_action

        com_el = MagicMock()
        # First poll returns different state
        com_el.CurrentIsEnabled = False

        result = verify_action(
            action="invoke",
            element_meta={"name": "OK"},
            pre_state=True,
            hwnd=HWND,
            com_element=com_el,
            timeout_ms=100,
        )

        assert result.method == "uia_state_check"
        assert result.passed is True

    @patch("src.utils.verification.time")
    def test_invoke_no_change_still_passes(self, mock_time):
        """Invoke with no state change still passes (fire-and-forget)."""
        from src.utils.verification import verify_action

        com_el = MagicMock()
        com_el.CurrentIsEnabled = True  # Same as pre_state

        result = verify_action(
            action="invoke",
            element_meta={"name": "OK"},
            pre_state=True,
            hwnd=HWND,
            com_element=com_el,
            timeout_ms=0,  # skip polling
        )

        assert result.passed is True

    @patch("src.utils.verification.time")
    def test_invoke_no_com_element_falls_to_screenshot(self, mock_time):
        """No COM element -> screenshot fallback."""
        from src.utils.verification import verify_action

        with patch("src.utils.verification._screenshot_fallback") as mock_ss:
            mock_ss.return_value = VerificationResult(
                method="screenshot", passed=True, detail="screenshot captured"
            )
            result = verify_action(
                action="invoke",
                element_meta={"name": "OK"},
                pre_state=None,
                hwnd=HWND,
                com_element=None,
                timeout_ms=100,
            )

            assert result.method == "screenshot"
            assert result.passed is True


class TestVerifySetValue:
    """Tests for set_value verification strategy."""

    @patch("src.utils.uia_patterns.get_value", return_value="hello")
    def test_set_value_match(self, mock_get_value):
        """Value matches expected -> success."""
        from src.utils.verification import verify_action

        com_el = MagicMock()

        result = verify_action(
            action="set_value",
            element_meta={"name": "Input"},
            pre_state="hello",
            hwnd=HWND,
            com_element=com_el,
        )
        assert result.passed is True
        assert result.method == "uia_state_check"

    @patch("src.utils.uia_patterns.get_value", return_value="hello")
    def test_set_value_direct_match(self, mock_get_value):
        """Directly test set_value verification with matching value."""
        from src.utils.verification import _verify_set_value

        com_el = MagicMock()
        result = _verify_set_value(
            com_element=com_el,
            pre_state="hello",
            timeout_ms=500,
        )

        assert result is not None
        assert result.passed is True

    @patch("src.utils.uia_patterns.get_value", return_value="wrong")
    def test_set_value_mismatch(self, mock_get_value):
        """Value does not match -> failure."""
        from src.utils.verification import _verify_set_value

        com_el = MagicMock()
        result = _verify_set_value(
            com_element=com_el,
            pre_state="expected",
            timeout_ms=500,
        )

        assert result is not None
        assert result.passed is False

    def test_set_value_no_element(self):
        """No COM element -> returns None (falls to screenshot)."""
        from src.utils.verification import _verify_set_value

        result = _verify_set_value(
            com_element=None,
            pre_state="hello",
            timeout_ms=500,
        )
        assert result is None


class TestVerifyToggle:
    """Tests for toggle verification strategy."""

    @patch("src.utils.uia_patterns.get_toggle_state", return_value=1)
    def test_toggle_state_changed(self, mock_get_state):
        """Toggle state changes -> success."""
        from src.utils.verification import _verify_toggle

        com_el = MagicMock()
        result = _verify_toggle(
            com_element=com_el,
            pre_state=0,
            timeout_ms=500,
        )

        assert result is not None
        assert result.passed is True

    @patch("src.utils.uia_patterns.get_toggle_state", return_value=0)
    def test_toggle_state_unchanged(self, mock_get_state):
        """Toggle state unchanged -> failure."""
        from src.utils.verification import _verify_toggle

        com_el = MagicMock()
        result = _verify_toggle(
            com_element=com_el,
            pre_state=0,
            timeout_ms=500,
        )

        assert result is not None
        assert result.passed is False

    def test_toggle_no_element(self):
        from src.utils.verification import _verify_toggle
        result = _verify_toggle(com_element=None, pre_state=0, timeout_ms=500)
        assert result is None


class TestVerifyExpand:
    """Tests for expand verification strategy."""

    @patch("src.utils.uia_patterns.get_expand_state", return_value=1)
    def test_expand_success(self, mock_get):
        from src.utils.verification import _verify_expand

        result = _verify_expand(com_element=MagicMock(), pre_state=0, timeout_ms=500)
        assert result is not None
        assert result.passed is True
        assert "Expanded" in result.detail

    @patch("src.utils.uia_patterns.get_expand_state", return_value=0)
    def test_expand_failure(self, mock_get):
        from src.utils.verification import _verify_expand

        result = _verify_expand(com_element=MagicMock(), pre_state=0, timeout_ms=500)
        assert result is not None
        assert result.passed is False


class TestVerifyCollapse:
    """Tests for collapse verification strategy."""

    @patch("src.utils.uia_patterns.get_expand_state", return_value=0)
    def test_collapse_success(self, mock_get):
        from src.utils.verification import _verify_collapse

        result = _verify_collapse(com_element=MagicMock(), pre_state=1, timeout_ms=500)
        assert result is not None
        assert result.passed is True
        assert "Collapsed" in result.detail

    @patch("src.utils.uia_patterns.get_expand_state", return_value=1)
    def test_collapse_failure(self, mock_get):
        from src.utils.verification import _verify_collapse

        result = _verify_collapse(com_element=MagicMock(), pre_state=1, timeout_ms=500)
        assert result is not None
        assert result.passed is False


class TestVerifySelect:
    """Tests for select verification strategy."""

    @patch("src.utils.uia_patterns.is_selected", return_value=True)
    def test_select_success(self, mock_sel):
        from src.utils.verification import _verify_select

        result = _verify_select(com_element=MagicMock(), pre_state=False, timeout_ms=500)
        assert result is not None
        assert result.passed is True

    @patch("src.utils.uia_patterns.is_selected", return_value=False)
    def test_select_failure(self, mock_sel):
        from src.utils.verification import _verify_select

        result = _verify_select(com_element=MagicMock(), pre_state=False, timeout_ms=500)
        assert result is not None
        assert result.passed is False


class TestVerifyScroll:
    """Tests for scroll verification strategy."""

    @patch("src.utils.uia_patterns.get_scroll_percent", return_value={"horizontal": 0, "vertical": 30})
    def test_scroll_changed(self, mock_scroll):
        from src.utils.verification import _verify_scroll

        pre = {"horizontal": 0, "vertical": 0}
        result = _verify_scroll(com_element=MagicMock(), pre_state=pre, timeout_ms=500)
        assert result is not None
        assert result.passed is True

    @patch("src.utils.uia_patterns.get_scroll_percent", return_value={"horizontal": 0, "vertical": 0})
    def test_scroll_unchanged(self, mock_scroll):
        from src.utils.verification import _verify_scroll

        pre = {"horizontal": 0, "vertical": 0}
        result = _verify_scroll(com_element=MagicMock(), pre_state=pre, timeout_ms=500)
        assert result is not None
        assert result.passed is False


class TestScreenshotFallback:
    """Tests for screenshot fallback."""

    @patch("src.utils.action_helpers._capture_post_action", return_value="/tmp/ss.png")
    def test_screenshot_fallback_success(self, mock_capture):
        from src.utils.verification import _screenshot_fallback

        result = _screenshot_fallback(HWND)
        assert result.method == "screenshot"
        assert result.passed is True

    @patch("src.utils.action_helpers._capture_post_action", side_effect=Exception("fail"))
    def test_screenshot_fallback_failure(self, mock_capture):
        from src.utils.verification import _screenshot_fallback

        result = _screenshot_fallback(HWND)
        assert result.method == "none"
        assert result.passed is False


class TestVerifyActionEdgeCases:
    """Edge case tests for verify_action."""

    def test_unknown_action(self):
        from src.utils.verification import verify_action

        result = verify_action(
            action="unknown_action",
            element_meta=None,
            pre_state=None,
            hwnd=HWND,
        )
        assert result.passed is False
        assert "No verification strategy" in result.detail

    def test_exception_during_verification(self):
        """COM exception -> VerificationResult with passed=False."""
        from src.utils.verification import verify_action

        com_el = MagicMock()
        com_el.CurrentIsEnabled = PropertyMock(side_effect=Exception("COM error"))

        # Mock the strategy to raise
        with patch("src.utils.verification._VERIFICATION_STRATEGIES", {"invoke": MagicMock(side_effect=Exception("boom"))}):
            result = verify_action(
                action="invoke",
                element_meta={"name": "OK"},
                pre_state=True,
                hwnd=HWND,
                com_element=com_el,
            )
            assert result.passed is False
            assert "boom" in result.detail
