"""Unit tests for vision fallback in cv_find when no matches are found."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models import Rect, ScreenshotResult, UiaElement


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_WINDOW_RECT = (0, 0, 1920, 1080)


def _make_uia_element(
    name: str = "",
    control_type: str = "Button",
    ref_id: str = "ref_1",
    rect: Rect | None = None,
    children: list | None = None,
) -> UiaElement:
    return UiaElement(
        ref_id=ref_id,
        name=name,
        control_type=control_type,
        rect=rect or Rect(x=100, y=100, width=80, height=30),
        value=None,
        children=children or [],
    )


def _make_screenshot_result(path: str = "C:/tmp/screenshot.png") -> ScreenshotResult:
    return ScreenshotResult(
        image_path=path,
        rect=Rect(x=0, y=0, width=1920, height=1080),
        physical_resolution={"width": 1920, "height": 1080},
        logical_resolution={"width": 1920, "height": 1080},
        dpi_scale=1.0,
        format="png",
    )


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


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """Clear the per-HWND cooldown dict before and after each test."""
    from src.tools.find import _screenshot_cooldowns
    _screenshot_cooldowns.clear()
    yield
    _screenshot_cooldowns.clear()


# ===========================================================================
# Test: Vision fallback on FIND_NO_MATCH
# ===========================================================================

class TestFindFallbackScreenshot:
    """Tests for the screenshot fallback when cv_find returns no matches."""

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window")
    def test_no_match_returns_image_path(self, mock_capture, mock_tree):
        """When no matches and capture succeeds, error should include image_path."""
        from src.tools.find import cv_find

        mock_capture.return_value = _make_screenshot_result("/tmp/test.png")

        result = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert result["success"] is False
        assert result["error"]["code"] == "FIND_NO_MATCH"
        assert result["error"]["image_path"] == "/tmp/test.png"
        assert "Use Read tool on image_path" in result["error"]["message"]

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window")
    def test_cooldown_prevents_second_screenshot(self, mock_capture, mock_tree):
        """Second call within cooldown should NOT include image_path."""
        from src.tools.find import cv_find, _screenshot_cooldowns

        mock_capture.return_value = _make_screenshot_result("/tmp/test.png")

        # First call -- should capture
        with patch("src.tools.find._time.monotonic", return_value=100.0):
            result1 = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert "image_path" in result1["error"]

        # Second call at 102s (within 5s cooldown) -- should NOT capture
        with patch("src.tools.find._time.monotonic", return_value=102.0):
            result2 = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert "image_path" not in result2["error"]

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window")
    def test_cooldown_allows_screenshot_after_expiry(self, mock_capture, mock_tree):
        """After cooldown expires, screenshot should be taken again."""
        from src.tools.find import cv_find

        mock_capture.return_value = _make_screenshot_result("/tmp/test.png")

        # First call at t=100
        with patch("src.tools.find._time.monotonic", return_value=100.0):
            result1 = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert "image_path" in result1["error"]

        # Second call at t=106 (>5s cooldown) -- should capture again
        with patch("src.tools.find._time.monotonic", return_value=106.0):
            result2 = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert "image_path" in result2["error"]

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window")
    def test_different_hwnds_independent_cooldowns(self, mock_capture, mock_tree):
        """Different HWNDs should have independent cooldowns."""
        from src.tools.find import cv_find

        mock_capture.return_value = _make_screenshot_result("/tmp/test.png")

        # Screenshot HWND 111 at t=100
        with patch("src.tools.find._time.monotonic", return_value=100.0):
            r1 = cv_find(query="nonexistent", hwnd=111, method="uia")
        assert "image_path" in r1["error"]

        # Screenshot HWND 222 at t=101 -- different HWND, should be allowed
        with patch("src.tools.find._time.monotonic", return_value=101.0):
            r2 = cv_find(query="nonexistent", hwnd=222, method="uia")
        assert "image_path" in r2["error"]

        # HWND 111 again at t=102 -- within cooldown, should NOT capture
        with patch("src.tools.find._time.monotonic", return_value=102.0):
            r3 = cv_find(query="nonexistent", hwnd=111, method="uia")
        assert "image_path" not in r3["error"]

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window", side_effect=Exception("Capture failed"))
    def test_capture_failure_returns_normal_error(self, mock_capture, mock_tree):
        """If capture_window raises, error should still be returned without image_path."""
        from src.tools.find import cv_find

        result = cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert result["success"] is False
        assert result["error"]["code"] == "FIND_NO_MATCH"
        assert "image_path" not in result["error"]

    @patch("src.tools.find.get_ui_tree")
    def test_successful_match_no_image_path(self, mock_tree):
        """When matches ARE found, response should NOT include image_path."""
        from src.tools.find import cv_find

        mock_tree.return_value = [
            _make_uia_element(name="Submit", control_type="Button", ref_id="ref_1"),
        ]

        result = cv_find(query="Submit", hwnd=12345, method="uia")

        assert result["success"] is True
        # Success responses should never have an error key with image_path
        assert "error" not in result or "image_path" not in result.get("error", {})

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window")
    def test_cooldown_dict_updated_on_capture(self, mock_capture, mock_tree):
        """After a successful capture, the cooldown dict should be updated."""
        from src.tools.find import cv_find, _screenshot_cooldowns

        mock_capture.return_value = _make_screenshot_result("/tmp/test.png")

        with patch("src.tools.find._time.monotonic", return_value=42.0):
            cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert 12345 in _screenshot_cooldowns
        assert _screenshot_cooldowns[12345] == 42.0

    @patch("src.tools.find.get_ui_tree", return_value=[])
    @patch("src.utils.screenshot.capture_window", side_effect=Exception("fail"))
    def test_capture_failure_does_not_update_cooldown(self, mock_capture, mock_tree):
        """If capture fails, cooldown dict should NOT be updated."""
        from src.tools.find import cv_find, _screenshot_cooldowns

        cv_find(query="nonexistent", hwnd=12345, method="uia")

        assert 12345 not in _screenshot_cooldowns
