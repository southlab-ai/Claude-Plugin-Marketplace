"""Unit tests for security utilities in src/utils/security.py."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

import pytest

from src.errors import AccessDeniedError, RateLimitedError
from src.utils.security import (
    check_restricted,
    check_rate_limit,
    redact_ocr_output,
    _sanitize_params,
)


class TestCheckRestricted:
    """Tests for check_restricted."""

    @patch("src.utils.security.config")
    def test_restricted_process_raises(self, mock_config):
        mock_config.RESTRICTED_PROCESSES = ["keepass", "1password"]
        with pytest.raises(AccessDeniedError):
            check_restricted("keepass")

    @patch("src.utils.security.config")
    def test_restricted_case_insensitive(self, mock_config):
        mock_config.RESTRICTED_PROCESSES = ["keepass"]
        # check_restricted lowercases the input before comparison
        with pytest.raises(AccessDeniedError):
            check_restricted("keepass")

    @patch("src.utils.security.config")
    def test_allowed_process_passes(self, mock_config):
        mock_config.RESTRICTED_PROCESSES = ["keepass", "1password"]
        # Should not raise
        check_restricted("notepad")

    @patch("src.utils.security.config")
    def test_empty_process_name(self, mock_config):
        mock_config.RESTRICTED_PROCESSES = ["keepass"]
        # Empty string should not match
        check_restricted("")

    @patch("src.utils.security.config")
    def test_empty_restricted_list(self, mock_config):
        mock_config.RESTRICTED_PROCESSES = []
        # Nothing is restricted
        check_restricted("keepass")


class TestCheckRateLimit:
    """Tests for check_rate_limit."""

    def setup_method(self):
        """Clear rate limiter state before each test."""
        from src.utils.security import _action_timestamps
        _action_timestamps.clear()

    @patch("src.utils.security.config")
    def test_under_limit_passes(self, mock_config):
        mock_config.RATE_LIMIT = 20
        # Should not raise for a single call
        check_rate_limit()

    @patch("src.utils.security.config")
    def test_at_limit_raises(self, mock_config):
        mock_config.RATE_LIMIT = 5
        # Fill up to the limit
        for _ in range(5):
            check_rate_limit()
        # Next call should raise
        with pytest.raises(RateLimitedError):
            check_rate_limit()

    @patch("src.utils.security.config")
    def test_old_timestamps_expire(self, mock_config):
        mock_config.RATE_LIMIT = 5
        from src.utils.security import _action_timestamps
        # Add old timestamps (more than 1 second ago)
        old = time.monotonic() - 2.0
        for _ in range(5):
            _action_timestamps.append(old)
        # Should not raise because old timestamps expire
        check_rate_limit()


class TestRedactOcrOutput:
    """Tests for redact_ocr_output."""

    @patch("src.utils.security.config")
    def test_no_patterns(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = []
        text, regions = redact_ocr_output("secret123", [])
        assert text == "secret123"

    @patch("src.utils.security.config")
    def test_single_pattern(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = [r"\d{3}-\d{2}-\d{4}"]
        text, regions = redact_ocr_output(
            "SSN: 123-45-6789",
            [{"text": "SSN: 123-45-6789", "bbox": {"x": 0, "y": 0, "width": 100, "height": 20}}],
        )
        assert "[REDACTED]" in text
        assert "123-45-6789" not in text
        assert "[REDACTED]" in regions[0]["text"]

    @patch("src.utils.security.config")
    def test_multiple_patterns(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = [r"\d{3}-\d{2}-\d{4}", r"password:\s*\S+"]
        text, regions = redact_ocr_output(
            "SSN: 123-45-6789 password: hunter2",
            [],
        )
        assert "123-45-6789" not in text
        assert "hunter2" not in text

    @patch("src.utils.security.config")
    def test_invalid_pattern_skipped(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = ["[invalid", r"\d+"]
        text, regions = redact_ocr_output("value 42", [])
        # Invalid pattern is skipped, valid pattern applies
        assert "42" not in text
        assert "[REDACTED]" in text

    @patch("src.utils.security.config")
    def test_empty_pattern_in_list(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = ["", r"\d+"]
        text, regions = redact_ocr_output("count 99", [])
        assert "99" not in text

    @patch("src.utils.security.config")
    def test_regions_redacted(self, mock_config):
        mock_config.OCR_REDACTION_PATTERNS = [r"secret"]
        regions = [
            {"text": "this is secret data", "bbox": {"x": 0, "y": 0, "width": 100, "height": 20}},
            {"text": "safe text", "bbox": {"x": 0, "y": 20, "width": 100, "height": 20}},
        ]
        text, out_regions = redact_ocr_output("this is secret data. safe text.", regions)
        assert "secret" not in text
        assert "secret" not in out_regions[0]["text"]
        assert out_regions[1]["text"] == "safe text"


class TestSanitizeParams:
    """Tests for _sanitize_params."""

    def test_text_param_redacted(self):
        result = _sanitize_params({"text": "hello world", "x": 100})
        assert result["x"] == 100
        assert "hello world" not in str(result["text"])
        assert "len=11" in result["text"]

    def test_non_text_params_preserved(self):
        result = _sanitize_params({"hwnd": 12345, "button": "left"})
        assert result["hwnd"] == 12345
        assert result["button"] == "left"

    def test_empty_text(self):
        result = _sanitize_params({"text": ""})
        assert "len=0" in result["text"]

    def test_empty_params(self):
        result = _sanitize_params({})
        assert result == {}

    def test_does_not_modify_original(self):
        original = {"text": "secret", "x": 50}
        result = _sanitize_params(original)
        assert original["text"] == "secret"  # Original unchanged
        assert "secret" not in str(result["text"])
