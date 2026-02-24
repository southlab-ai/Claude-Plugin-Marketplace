"""Unit tests for configuration loading in src/config.py."""

from __future__ import annotations

import pytest


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_restricted_processes(self):
        from src import config

        assert isinstance(config.RESTRICTED_PROCESSES, list)
        assert "keepass" in config.RESTRICTED_PROCESSES
        assert "1password" in config.RESTRICTED_PROCESSES
        assert "bitwarden" in config.RESTRICTED_PROCESSES

    def test_default_dry_run(self):
        from src import config
        assert config.DRY_RUN is False

    def test_default_max_width(self):
        from src import config
        assert config.DEFAULT_MAX_WIDTH == 1280

    def test_default_max_text_length(self):
        from src import config
        assert config.MAX_TEXT_LENGTH == 1000

    def test_default_rate_limit(self):
        from src import config
        assert config.RATE_LIMIT == 20

    def test_default_max_wait_timeout(self):
        from src import config
        assert config.MAX_WAIT_TIMEOUT == 60.0

    def test_default_max_simple_wait(self):
        from src import config
        assert config.MAX_SIMPLE_WAIT == 30.0

    def test_default_uia_depth(self):
        from src import config
        assert config.DEFAULT_UIA_DEPTH == 5

    def test_default_uia_timeout(self):
        from src import config
        assert config.UIA_TIMEOUT == 5.0

    def test_default_ocr_redaction_patterns(self):
        from src import config
        assert isinstance(config.OCR_REDACTION_PATTERNS, list)

    def test_audit_log_path_is_path(self):
        from src import config
        from pathlib import Path
        assert isinstance(config.AUDIT_LOG_PATH, Path)


class TestConfigEnvOverrides:
    """Test configuration loading from environment variables."""

    def test_dry_run_env_true(self, monkeypatch):
        monkeypatch.setenv("CV_DRY_RUN", "true")
        # Re-import to pick up env change
        import importlib
        from src import config
        importlib.reload(config)
        assert config.DRY_RUN is True
        # Reset
        monkeypatch.delenv("CV_DRY_RUN", raising=False)
        importlib.reload(config)

    def test_dry_run_env_false(self, monkeypatch):
        monkeypatch.setenv("CV_DRY_RUN", "false")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.DRY_RUN is False
        monkeypatch.delenv("CV_DRY_RUN", raising=False)
        importlib.reload(config)

    def test_max_width_env(self, monkeypatch):
        monkeypatch.setenv("CV_DEFAULT_MAX_WIDTH", "1920")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.DEFAULT_MAX_WIDTH == 1920
        monkeypatch.delenv("CV_DEFAULT_MAX_WIDTH", raising=False)
        importlib.reload(config)

    def test_max_width_invalid_env(self, monkeypatch):
        monkeypatch.setenv("CV_DEFAULT_MAX_WIDTH", "not_a_number")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.DEFAULT_MAX_WIDTH == 1280  # default
        monkeypatch.delenv("CV_DEFAULT_MAX_WIDTH", raising=False)
        importlib.reload(config)

    def test_rate_limit_env(self, monkeypatch):
        monkeypatch.setenv("CV_RATE_LIMIT", "50")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.RATE_LIMIT == 50
        monkeypatch.delenv("CV_RATE_LIMIT", raising=False)
        importlib.reload(config)

    def test_restricted_processes_env(self, monkeypatch):
        monkeypatch.setenv("CV_RESTRICTED_PROCESSES", "foo,bar,baz")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.RESTRICTED_PROCESSES == ["foo", "bar", "baz"]
        monkeypatch.delenv("CV_RESTRICTED_PROCESSES", raising=False)
        importlib.reload(config)

    def test_restricted_processes_whitespace(self, monkeypatch):
        monkeypatch.setenv("CV_RESTRICTED_PROCESSES", " foo , bar ")
        import importlib
        from src import config
        importlib.reload(config)
        assert config.RESTRICTED_PROCESSES == ["foo", "bar"]
        monkeypatch.delenv("CV_RESTRICTED_PROCESSES", raising=False)
        importlib.reload(config)

    def test_audit_log_path_env(self, monkeypatch):
        monkeypatch.setenv("CV_AUDIT_LOG_PATH", "/tmp/test_audit.jsonl")
        import importlib
        from src import config
        from pathlib import Path
        importlib.reload(config)
        assert config.AUDIT_LOG_PATH == Path("/tmp/test_audit.jsonl")
        monkeypatch.delenv("CV_AUDIT_LOG_PATH", raising=False)
        importlib.reload(config)


class TestHelperFunctions:
    """Test the internal config helper functions."""

    def test_get_env_list_empty(self, monkeypatch):
        from src.config import _get_env_list
        result = _get_env_list("NONEXISTENT_KEY_12345", "")
        assert result == []

    def test_get_env_list_with_values(self, monkeypatch):
        from src.config import _get_env_list
        monkeypatch.setenv("TEST_LIST", "a,b,c")
        result = _get_env_list("TEST_LIST", "")
        assert result == ["a", "b", "c"]

    def test_get_env_bool_defaults(self):
        from src.config import _get_env_bool
        assert _get_env_bool("NONEXISTENT_KEY_12345", True) is True
        assert _get_env_bool("NONEXISTENT_KEY_12345", False) is False

    def test_get_env_bool_truthy(self, monkeypatch):
        from src.config import _get_env_bool
        for val in ("true", "1", "yes", "True", "YES"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _get_env_bool("TEST_BOOL", False) is True

    def test_get_env_bool_falsy(self, monkeypatch):
        from src.config import _get_env_bool
        for val in ("false", "0", "no"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert _get_env_bool("TEST_BOOL", True) is False

    def test_get_env_int_default(self):
        from src.config import _get_env_int
        assert _get_env_int("NONEXISTENT_KEY_12345", 42) == 42

    def test_get_env_int_valid(self, monkeypatch):
        from src.config import _get_env_int
        monkeypatch.setenv("TEST_INT", "99")
        assert _get_env_int("TEST_INT", 0) == 99

    def test_get_env_int_invalid(self, monkeypatch):
        from src.config import _get_env_int
        monkeypatch.setenv("TEST_INT", "abc")
        assert _get_env_int("TEST_INT", 42) == 42
