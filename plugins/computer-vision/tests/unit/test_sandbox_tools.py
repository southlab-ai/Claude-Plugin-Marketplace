"""Unit tests for sandbox MCP tools (src/tools/sandbox.py).

All tests mock the IPC and lifecycle layers — no real sandbox needed.
"""

from __future__ import annotations

import base64
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.tools.sandbox import (
    _SandboxState,
    _state,
    validate_sandbox_ready,
    _record_action,
    _sandbox_status_text,
    _save_screenshot_to_temp,
    cv_sandbox_start,
    cv_sandbox_stop,
    cv_sandbox_click,
    cv_sandbox_type,
    cv_sandbox_screenshot,
    cv_sandbox_scene,
    cv_session_status,
    cv_sandbox_batch,
    cv_sandbox_check,
    BatchAction,
    BatchResult,
    SessionStatus,
)
import src.tools.sandbox as sandbox_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module state before and after each test."""
    sandbox_module._state = _SandboxState()
    yield
    sandbox_module._state = _SandboxState()


@pytest.fixture
def mock_manager():
    """Create a mock SandboxLifecycleManager."""
    mgr = MagicMock()
    mgr.is_ready.return_value = True
    mgr.start.return_value = True
    mgr.get_connection_info.return_value = ("127.0.0.1", 49152, "abc123")
    mgr._process = MagicMock()
    mgr._process.pid = 1234
    return mgr


@pytest.fixture
def mock_ipc():
    """Create a mock ShimIPCClient."""
    client = MagicMock()
    client.connected = True
    client.send_request.return_value = {}
    return client


@pytest.fixture
def ready_state(mock_manager, mock_ipc):
    """Set up module state as if sandbox is running."""
    sandbox_module._state.manager = mock_manager
    sandbox_module._state.ipc_client = mock_ipc
    sandbox_module._state.start_time = time.time()
    sandbox_module._state.action_history = []
    return sandbox_module._state


# ---------------------------------------------------------------------------
# Tests: validate_sandbox_ready
# ---------------------------------------------------------------------------


class TestValidateSandboxReady:
    def test_not_started(self):
        assert "not started" in validate_sandbox_ready().lower()

    def test_manager_not_ready(self, mock_manager, mock_ipc):
        mock_manager.is_ready.return_value = False
        sandbox_module._state.manager = mock_manager
        sandbox_module._state.ipc_client = mock_ipc
        assert "not ready" in validate_sandbox_ready().lower()

    def test_ipc_not_connected(self, mock_manager, mock_ipc):
        mock_ipc.connected = False
        sandbox_module._state.manager = mock_manager
        sandbox_module._state.ipc_client = mock_ipc
        assert "disconnected" in validate_sandbox_ready().lower()

    def test_ready(self, ready_state):
        assert validate_sandbox_ready() is None


# ---------------------------------------------------------------------------
# Tests: helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_record_action(self):
        sandbox_module._state.action_history = []
        _record_action("click", {"x": 10, "y": 20})
        assert len(sandbox_module._state.action_history) == 1
        assert sandbox_module._state.action_history[0]["action"] == "click"

    def test_record_action_caps_at_100(self):
        sandbox_module._state.action_history = [{"action": f"a{i}"} for i in range(100)]
        _record_action("overflow", {})
        assert len(sandbox_module._state.action_history) == 100

    def test_sandbox_status_text(self):
        sandbox_module._state.action_history = [{"action": "a"}] * 5
        text = _sandbox_status_text()
        assert "5 actions" in text

    def test_save_screenshot_to_temp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sandbox_module, "_SCREENSHOT_DIR", tmp_path)
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = _save_screenshot_to_temp(png_data)
        assert "sandbox_" in path
        assert path.endswith(".png")


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_start
# ---------------------------------------------------------------------------


class TestCvSandboxStart:
    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient")
    @patch("src.sandbox.lifecycle.sandbox_manager.SandboxLifecycleManager")
    def test_start_success(self, MockManager, MockIPC):
        mgr = MockManager.return_value
        mgr.start.return_value = True
        mgr.get_connection_info.return_value = ("127.0.0.1", 49152, "tok")
        mgr._process = MagicMock()
        mgr._process.pid = 5678

        ipc = MockIPC.return_value
        ipc.connected = True

        with patch.object(sandbox_module, "_DLL_FOLDER", new=MagicMock(is_dir=MagicMock(return_value=True))):
            result = cv_sandbox_start("C:\\app.exe")

        assert result["success"] is True
        assert result["sandbox_pid"] == 5678
        assert result["shim_port"] == 49152

    @patch("src.sandbox.ipc.shim_ipc_client.ShimIPCClient")
    @patch("src.sandbox.lifecycle.sandbox_manager.SandboxLifecycleManager")
    def test_start_sandbox_failure(self, MockManager, MockIPC):
        mgr = MockManager.return_value
        mgr.start.return_value = False

        with patch.object(sandbox_module, "_DLL_FOLDER", new=MagicMock(is_dir=MagicMock(return_value=True))):
            result = cv_sandbox_start("C:\\app.exe")

        assert result["success"] is False
        assert "Failed to start" in result["error"]["message"]

    def test_start_no_dll_folder(self):
        with patch.object(sandbox_module, "_DLL_FOLDER", new=MagicMock(is_dir=MagicMock(return_value=False))):
            result = cv_sandbox_start("C:\\app.exe")
        assert result["success"] is False
        assert "DLL folder" in result["error"]["message"]


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_stop
# ---------------------------------------------------------------------------


class TestCvSandboxStop:
    def test_stop_no_session(self):
        result = cv_sandbox_stop()
        assert result["success"] is False

    def test_stop_running_session(self, ready_state):
        result = cv_sandbox_stop()
        assert result["success"] is True
        assert sandbox_module._state.manager is None

    def test_stop_handles_cleanup_error(self, ready_state):
        ready_state.ipc_client.close.side_effect = RuntimeError("close failed")
        result = cv_sandbox_stop()
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_click
# ---------------------------------------------------------------------------


class TestCvSandboxClick:
    def test_click_success(self, ready_state):
        result = cv_sandbox_click(100, 200)
        assert result["success"] is True
        assert "sandbox_status" in result
        ready_state.ipc_client.send_request.assert_called_with(
            "inject_click", {"x": 100, "y": 200}
        )

    def test_click_not_ready(self):
        result = cv_sandbox_click(100, 200)
        assert result["success"] is False

    def test_click_ipc_failure(self, ready_state):
        ready_state.ipc_client.send_request.side_effect = ConnectionError("lost")
        result = cv_sandbox_click(100, 200)
        assert result["success"] is False
        assert "failed" in result["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_type
# ---------------------------------------------------------------------------


class TestCvSandboxType:
    def test_type_success(self, ready_state):
        result = cv_sandbox_type("hello world")
        assert result["success"] is True
        ready_state.ipc_client.send_request.assert_called_with(
            "inject_keys", {"text": "hello world"}
        )

    def test_type_not_ready(self):
        result = cv_sandbox_type("text")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_screenshot
# ---------------------------------------------------------------------------


class TestCvSandboxScreenshot:
    def test_screenshot_success(self, ready_state, tmp_path, monkeypatch):
        monkeypatch.setattr(sandbox_module, "_SCREENSHOT_DIR", tmp_path)
        png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()
        ready_state.ipc_client.send_request.return_value = {"data_b64": png_b64}

        result = cv_sandbox_screenshot()
        assert result["success"] is True
        assert "image_path" in result
        assert result["image_path"].endswith(".png")

    def test_screenshot_empty_frame(self, ready_state):
        ready_state.ipc_client.send_request.return_value = {"data_b64": ""}
        result = cv_sandbox_screenshot()
        assert result["success"] is False

    def test_screenshot_not_ready(self):
        result = cv_sandbox_screenshot()
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_scene
# ---------------------------------------------------------------------------


class TestCvSandboxScene:
    def test_scene_success(self, ready_state):
        ready_state.ipc_client.send_request.return_value = {
            "version": 1,
            "timestamp_ms": 1000,
            "stale": False,
            "windows": [],
            "text_elements": [],
        }
        result = cv_sandbox_scene()
        assert result["success"] is True
        assert "scene" in result
        assert result["scene"]["version"] == 1

    def test_scene_not_ready(self):
        result = cv_sandbox_scene()
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: cv_session_status
# ---------------------------------------------------------------------------


class TestCvSessionStatus:
    def test_status_running(self, ready_state):
        _record_action("click", {"x": 1, "y": 2})
        _record_action("type", {"text": "hi"})
        result = cv_session_status()
        assert result["success"] is True
        status = result["status"]
        assert status["sandbox_running"] is True
        assert status["shim_connected"] is True
        assert status["total_actions"] == 2
        assert len(status["last_5_actions"]) == 2

    def test_status_not_running(self):
        result = cv_session_status()
        assert result["success"] is True
        status = result["status"]
        assert status["sandbox_running"] is False
        assert status["shim_connected"] is False
        assert status["total_actions"] == 0


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_batch
# ---------------------------------------------------------------------------


class TestCvSandboxBatch:
    def test_batch_empty(self, ready_state):
        result = cv_sandbox_batch([])
        assert result["success"] is False

    def test_batch_too_many(self, ready_state):
        plan = [{"action": "click", "params": {"x": 0, "y": 0}}] * 21
        result = cv_sandbox_batch(plan)
        assert result["success"] is False
        assert "max" in result["error"]["message"].lower()

    def test_batch_success(self, ready_state):
        plan = [
            {"action": "click", "params": {"x": 10, "y": 20}},
            {"action": "type", "params": {"text": "hello"}},
        ]
        result = cv_sandbox_batch(plan)
        assert result["success"] is True
        batch = result["result"]
        assert batch["completed_count"] == 2
        assert batch["all_passed"] is True
        assert batch["batch_status"] == "completed"

    def test_batch_with_checkpoint(self, ready_state, tmp_path, monkeypatch):
        monkeypatch.setattr(sandbox_module, "_SCREENSHOT_DIR", tmp_path)
        png_b64 = base64.b64encode(b"\x89PNG" + b"\x00" * 50).decode()
        ready_state.ipc_client.send_request.return_value = {"data_b64": png_b64}

        plan = [
            {"action": "click", "params": {"x": 10, "y": 20}, "checkpoint": True},
        ]
        result = cv_sandbox_batch(plan)
        assert result["success"] is True
        assert len(result["result"]["checkpoints"]) == 1

    def test_batch_abort_on_assertion_failure(self, ready_state):
        plan = [
            {
                "action": "click",
                "params": {"x": 10, "y": 20},
                "assert_field": {"result": "WRONG"},
            },
            {"action": "type", "params": {"text": "never reached"}},
        ]
        result = cv_sandbox_batch(plan, on_failure="abort")
        assert result["success"] is True
        batch = result["result"]
        assert batch["batch_status"] == "aborted"
        assert batch["failed_index"] == 0
        assert batch["completed_count"] == 1  # only the first step executed

    def test_batch_continue_on_failure(self, ready_state):
        plan = [
            {
                "action": "click",
                "params": {"x": 10, "y": 20},
                "assert_field": {"result": "WRONG"},
            },
            {"action": "type", "params": {"text": "still runs"}},
        ]
        result = cv_sandbox_batch(plan, on_failure="continue")
        assert result["success"] is True
        batch = result["result"]
        assert batch["batch_status"] == "partial"
        assert batch["completed_count"] == 2  # both steps executed

    def test_batch_not_ready(self):
        plan = [{"action": "click", "params": {"x": 0, "y": 0}}]
        result = cv_sandbox_batch(plan)
        assert result["success"] is False

    def test_batch_invalid_on_failure(self, ready_state):
        plan = [{"action": "click", "params": {"x": 0, "y": 0}}]
        result = cv_sandbox_batch(plan, on_failure="explode")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: cv_sandbox_check
# ---------------------------------------------------------------------------


class TestCvSandboxCheck:
    @patch("src.tools.sandbox.subprocess.run")
    def test_check_basic(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = cv_sandbox_check()
        assert result["success"] is True
        assert "windows_edition" in result
        assert "recommended_mode" in result

    @patch("src.tools.sandbox.subprocess.run")
    def test_check_with_sandbox(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        # Mock WindowsSandbox.exe existence
        with patch("src.tools.sandbox.Path.exists", return_value=True):
            result = cv_sandbox_check()
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tests: Pydantic models
# ---------------------------------------------------------------------------


class TestModels:
    def test_session_status_defaults(self):
        s = SessionStatus(sandbox_running=False, shim_connected=False)
        assert s.total_actions == 0
        assert s.last_5_actions == []

    def test_batch_action_defaults(self):
        a = BatchAction(action="click", params={"x": 0, "y": 0})
        assert a.checkpoint is False
        assert a.assert_field is None

    def test_batch_result_defaults(self):
        r = BatchResult()
        assert r.completed_count == 0
        assert r.all_passed is True
        assert r.batch_status == "completed"
