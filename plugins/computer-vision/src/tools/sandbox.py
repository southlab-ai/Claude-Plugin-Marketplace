"""MCP tools for Windows Sandbox automation — 8 tools for isolated desktop control.

These tools allow Claude Code agents to launch, interact with, and observe
applications inside Windows Sandbox while the user continues working
undisturbed on their desktop.

Tools call ShimIPCClient.send_request() directly (not through
SandboxShimAdapter) to avoid probe overhead on every call.
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.server import mcp
from src.errors import make_error, make_success, INVALID_INPUT, INPUT_FAILED
from src.utils.security import check_rate_limit, guard_dry_run, log_action

logger = logging.getLogger(__name__)

# Screenshot temp directory (shared with existing tools)
_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "cv_plugin_screenshots"

# DLL folder for sandbox mapped folders
_DLL_FOLDER = Path(__file__).resolve().parent.parent / "sandbox" / "native" / "build"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SessionStatus(BaseModel):
    """Structured status of the sandbox session."""

    sandbox_running: bool
    shim_connected: bool
    shim_port: int | None = None
    scene_graph_version: int = 0
    total_actions: int = 0
    last_action: dict | None = None
    last_5_actions: list[dict] = Field(default_factory=list)
    uptime_s: float | None = None
    last_heartbeat_ms: int | None = None


class BatchAction(BaseModel):
    """A single action in a batch plan."""

    action: Literal["click", "type", "screenshot", "scene"]
    params: dict = Field(default_factory=dict)
    checkpoint: bool = False
    assert_field: dict | None = None


class BatchResult(BaseModel):
    """Result of a batch execution."""

    steps: list[dict] = Field(default_factory=list)
    completed_count: int = 0
    failed_index: int | None = None
    all_passed: bool = True
    checkpoints: list[str] = Field(default_factory=list)
    batch_status: Literal["completed", "aborted", "partial"] = "completed"


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------


@dataclass
class _SandboxState:
    """Private module state for the sandbox session."""

    manager: Any = None  # SandboxLifecycleManager
    ipc_client: Any = None  # ShimIPCClient
    adapter: Any = None  # SandboxShimAdapter
    action_history: list[dict] = field(default_factory=list)
    start_time: float | None = None


_state = _SandboxState()

# Max batch actions
_MAX_BATCH_ACTIONS = 20

# Default batch step timeout
_BATCH_STEP_TIMEOUT_S = 3.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_sandbox_ready() -> str | None:
    """Check that the sandbox is running and IPC is connected.

    Returns None if ready, or an error message string if not.
    """
    if _state.manager is None:
        return "Sandbox not started. Call cv_sandbox_start first."
    if not _state.manager.is_ready():
        return "Sandbox is not ready. It may have crashed or timed out."
    if _state.ipc_client is None:
        return "IPC client not initialized."
    if not _state.ipc_client.connected:
        return "IPC client disconnected from sandbox shim."
    return None


def _record_action(action_name: str, params: dict, result: str = "ok") -> None:
    """Record an action in the history for session status tracking."""
    entry = {
        "action": action_name,
        "params": params,
        "result": result,
        "timestamp": time.time(),
    }
    _state.action_history.append(entry)
    # Keep last 100 actions
    if len(_state.action_history) > 100:
        _state.action_history = _state.action_history[-100:]


def _sandbox_status_text() -> str:
    """Generate inline progress text for mutating tool responses."""
    count = len(_state.action_history)
    return f"Sandbox healthy, {count} actions completed"


def _save_screenshot_to_temp(png_data: bytes) -> str:
    """Save PNG bytes to a temp file and return the path."""
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    filename = f"sandbox_{timestamp}.png"
    filepath = _SCREENSHOT_DIR / filename
    filepath.write_bytes(png_data)
    return str(filepath)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def cv_sandbox_start(exe_path: str, timeout: float = 30.0) -> dict:
    """Launch Windows Sandbox and prepare it for automation.

    Starts a fresh sandbox instance, injects the shim DLL into the target
    application, and establishes the IPC connection. The user's desktop
    is completely undisturbed — all input goes to the isolated sandbox.

    Args:
        exe_path: Path to the executable to run inside the sandbox.
        timeout: Maximum seconds to wait for sandbox + shim readiness (default 30).
    """
    global _state

    # Stop any existing session
    if _state.manager is not None:
        try:
            _state.ipc_client.close() if _state.ipc_client else None
            _state.manager.stop()
        except Exception:
            pass
        _state = _SandboxState()

    try:
        from src.sandbox.lifecycle.sandbox_manager import SandboxLifecycleManager
        from src.sandbox.ipc.shim_ipc_client import ShimIPCClient

        # Verify DLL folder exists
        if not _DLL_FOLDER.is_dir():
            return make_error(
                INVALID_INPUT,
                f"Native DLL folder not found at {_DLL_FOLDER}. "
                f"Run: uv run python scripts/build_native.py",
            )

        # Create and start lifecycle manager
        manager = SandboxLifecycleManager(dll_folder=_DLL_FOLDER)
        ok = manager.start(exe_path=exe_path, timeout=timeout)
        if not ok:
            return make_error(
                INPUT_FAILED,
                "Failed to start Windows Sandbox. Check that Windows Sandbox "
                "feature is enabled (Windows Pro/Enterprise required). "
                "Use cv_sandbox_check for diagnostics.",
            )

        # Connect IPC client
        host, port, token = manager.get_connection_info()
        ipc_client = ShimIPCClient()
        ipc_client.connect(host=host, port=port, token=token)

        # Store state
        _state.manager = manager
        _state.ipc_client = ipc_client
        _state.start_time = time.time()
        _state.action_history = []

        log_action("cv_sandbox_start", {"exe_path": exe_path}, "ok")

        return make_success(
            sandbox_pid=manager._process.pid if manager._process else 0,
            shim_port=port,
        )

    except Exception as exc:
        log_action("cv_sandbox_start", {"exe_path": exe_path}, "error")
        # Clean up on failure
        _state = _SandboxState()
        return make_error(INPUT_FAILED, f"Sandbox start failed: {exc}")


@mcp.tool()
def cv_sandbox_stop() -> dict:
    """Stop the sandbox and clean up all resources.

    Closes the IPC connection, terminates the sandbox process, and
    removes temporary files.
    """
    global _state

    if _state.manager is None:
        return make_error(INVALID_INPUT, "No sandbox session to stop.")

    try:
        if _state.ipc_client is not None:
            _state.ipc_client.close()
        _state.manager.stop()
    except Exception as exc:
        logger.warning("Error during sandbox cleanup: %s", exc)

    _state = _SandboxState()
    log_action("cv_sandbox_stop", {}, "ok")
    return make_success(message="Sandbox stopped")


@mcp.tool()
def cv_sandbox_click(x: int, y: int) -> dict:
    """Click at coordinates inside the sandbox.

    Injects a mouse click at the specified position within the sandboxed
    application. Does NOT move the user's physical cursor.

    Args:
        x: X coordinate in sandbox screen pixels.
        y: Y coordinate in sandbox screen pixels.
    """
    # Security gate (mutating)
    not_ready = validate_sandbox_ready()
    if not_ready:
        return make_error(INVALID_INPUT, not_ready)
    check_rate_limit()
    dry = guard_dry_run("cv_sandbox_click", {"x": x, "y": y})
    if dry is not None:
        return dry

    try:
        _state.ipc_client.send_request("inject_click", {"x": x, "y": y})
        _record_action("click", {"x": x, "y": y})
        log_action("cv_sandbox_click", {"x": x, "y": y}, "ok")
        return make_success(sandbox_status=_sandbox_status_text())
    except Exception as exc:
        _record_action("click", {"x": x, "y": y}, "error")
        log_action("cv_sandbox_click", {"x": x, "y": y}, "error")
        return make_error(INPUT_FAILED, f"Sandbox click failed: {exc}")


@mcp.tool()
def cv_sandbox_type(text: str) -> dict:
    """Type text inside the sandbox.

    Injects keystrokes into the sandboxed application. Does NOT
    affect the user's keyboard input.

    Args:
        text: The text string to type.
    """
    # Security gate (mutating)
    not_ready = validate_sandbox_ready()
    if not_ready:
        return make_error(INVALID_INPUT, not_ready)
    check_rate_limit()
    dry = guard_dry_run("cv_sandbox_type", {"text": text})
    if dry is not None:
        return dry

    try:
        _state.ipc_client.send_request("inject_keys", {"text": text})
        _record_action("type", {"text_len": len(text)})
        log_action("cv_sandbox_type", {"text": text}, "ok")
        return make_success(sandbox_status=_sandbox_status_text())
    except Exception as exc:
        _record_action("type", {"text_len": len(text)}, "error")
        log_action("cv_sandbox_type", {"text": text}, "error")
        return make_error(INPUT_FAILED, f"Sandbox type failed: {exc}")


@mcp.tool()
def cv_sandbox_screenshot() -> dict:
    """Capture a screenshot of the sandboxed application.

    Returns an image_path that Claude can Read to visually inspect
    the current state of the sandbox.
    """
    not_ready = validate_sandbox_ready()
    if not_ready:
        return make_error(INVALID_INPUT, not_ready)

    try:
        result = _state.ipc_client.send_request(
            "capture_frame", {"format": "png"}, timeout=10.0
        )

        # Decode the base64 PNG data
        data_b64 = result.get("data_b64", "")
        if not data_b64:
            return make_error(INPUT_FAILED, "Shim returned empty frame data")

        png_data = base64.b64decode(data_b64)

        # Validate size
        if len(png_data) > 16 * 1024 * 1024:
            return make_error(INPUT_FAILED, "Frame exceeds 16MB size limit")

        # Save to temp file
        image_path = _save_screenshot_to_temp(png_data)
        _record_action("screenshot", {"size_bytes": len(png_data)})
        log_action("cv_sandbox_screenshot", {}, "ok")
        return make_success(image_path=image_path)

    except Exception as exc:
        log_action("cv_sandbox_screenshot", {}, "error")
        return make_error(INPUT_FAILED, f"Screenshot capture failed: {exc}")


@mcp.tool()
def cv_sandbox_scene() -> dict:
    """Get the scene graph of the sandboxed application.

    Returns the full UI element tree including windows, text elements,
    and their bounding rectangles as detected by the shim DLL hooks.
    """
    not_ready = validate_sandbox_ready()
    if not_ready:
        return make_error(INVALID_INPUT, not_ready)

    try:
        from src.sandbox.models.scene_graph import SceneGraphSnapshot

        result = _state.ipc_client.send_request("get_scene_graph")
        snapshot = SceneGraphSnapshot.model_validate(result)
        log_action("cv_sandbox_scene", {}, "ok")
        return make_success(scene=snapshot.model_dump())

    except Exception as exc:
        log_action("cv_sandbox_scene", {}, "error")
        return make_error(INPUT_FAILED, f"Scene graph fetch failed: {exc}")


@mcp.tool()
def cv_session_status() -> dict:
    """Get the current sandbox session status.

    Returns structured information about the sandbox state including
    connection health, action count, and recent action history.
    """
    sandbox_running = (
        _state.manager is not None and _state.manager.is_ready()
    )
    shim_connected = (
        _state.ipc_client is not None and _state.ipc_client.connected
    )
    shim_port = None
    if _state.manager is not None:
        try:
            _, port, _ = _state.manager.get_connection_info()
            shim_port = port
        except Exception:
            pass

    uptime_s = None
    if _state.start_time is not None:
        uptime_s = round(time.time() - _state.start_time, 1)

    last_5 = _state.action_history[-5:] if _state.action_history else []
    last_action = _state.action_history[-1] if _state.action_history else None

    status = SessionStatus(
        sandbox_running=sandbox_running,
        shim_connected=shim_connected,
        shim_port=shim_port,
        total_actions=len(_state.action_history),
        last_action=last_action,
        last_5_actions=last_5,
        uptime_s=uptime_s,
    )

    log_action("cv_session_status", {}, "ok")
    return make_success(status=status.model_dump())


@mcp.tool()
def cv_sandbox_batch(plan: list[dict], on_failure: str = "abort") -> dict:
    """Execute a batch of actions in the sandbox.

    Reduces IPC round-trips by executing multiple actions in sequence
    with optional checkpoints (screenshots) and assertions.

    Args:
        plan: List of action dicts, each with keys:
            - action: "click" | "type" | "screenshot" | "scene"
            - params: dict of action parameters (e.g., {"x": 100, "y": 200})
            - checkpoint: bool — capture screenshot at this step (default False)
            - assert_field: dict — optional assertion on result (e.g., {"success": True})
        on_failure: What to do when an assertion fails:
            - "abort" (default): stop and return partial results
            - "continue": skip failed step, continue remaining
            - "skip": same as continue
    """
    # Validate inputs
    if not plan:
        return make_error(INVALID_INPUT, "Batch plan is empty")
    if len(plan) > _MAX_BATCH_ACTIONS:
        return make_error(
            INVALID_INPUT,
            f"Batch plan has {len(plan)} actions, max is {_MAX_BATCH_ACTIONS}",
        )
    if on_failure not in ("abort", "continue", "skip"):
        return make_error(INVALID_INPUT, f"Invalid on_failure: {on_failure!r}")

    # Security gate (mutating)
    not_ready = validate_sandbox_ready()
    if not_ready:
        return make_error(INVALID_INPUT, not_ready)
    check_rate_limit()
    dry = guard_dry_run("cv_sandbox_batch", {"plan_size": len(plan)})
    if dry is not None:
        return dry

    # Parse actions
    actions: list[BatchAction] = []
    for i, raw in enumerate(plan):
        try:
            actions.append(BatchAction.model_validate(raw))
        except Exception as exc:
            return make_error(INVALID_INPUT, f"Invalid action at index {i}: {exc}")

    # Execute
    steps: list[dict] = []
    checkpoints: list[str] = []
    failed_index: int | None = None
    all_passed = True

    for i, action in enumerate(actions):
        # Time-share check between steps
        try:
            from src.utils.idle_check import is_user_idle
            if not is_user_idle(threshold_ms=2000):
                # User is active — pause briefly
                time.sleep(0.5)
        except ImportError:
            pass

        step_result = _execute_batch_step(action)
        steps.append(step_result)

        # Checkpoint screenshot
        if action.checkpoint:
            try:
                frame = _state.ipc_client.send_request(
                    "capture_frame", {"format": "png"}, timeout=10.0
                )
                data_b64 = frame.get("data_b64", "")
                if data_b64:
                    png_data = base64.b64decode(data_b64)
                    path = _save_screenshot_to_temp(png_data)
                    checkpoints.append(path)
            except Exception as exc:
                logger.warning("Checkpoint screenshot failed at step %d: %s", i, exc)

        # Assertion check
        if action.assert_field is not None:
            assertion_passed = _check_assertion(step_result, action.assert_field)
            if not assertion_passed:
                all_passed = False
                failed_index = i
                if on_failure == "abort":
                    break
                # continue/skip: mark failure but keep going

        _record_action(
            f"batch_{action.action}",
            action.params,
            step_result.get("result", "ok"),
        )

    completed_count = len(steps)
    if failed_index is not None and on_failure == "abort":
        batch_status = "aborted"
    elif failed_index is not None:
        batch_status = "partial"
    else:
        batch_status = "completed"

    result = BatchResult(
        steps=steps,
        completed_count=completed_count,
        failed_index=failed_index,
        all_passed=all_passed,
        checkpoints=checkpoints,
        batch_status=batch_status,
    )

    log_action("cv_sandbox_batch", {"steps": len(plan), "status": batch_status}, "ok")
    return make_success(
        result=result.model_dump(),
        sandbox_status=_sandbox_status_text(),
    )


@mcp.tool()
def cv_sandbox_check() -> dict:
    """Check if Windows Sandbox is available on this system.

    Reports Windows edition, Hyper-V status, and whether sandbox
    mode is available. Recommends the best automation mode:
    - "sandbox": Full isolation (Windows Pro/Enterprise with Sandbox enabled)
    - "time-share": Shared desktop with idle detection (Windows Home)
    - "desktop-only": Direct SendInput (no isolation)
    """
    result: dict[str, Any] = {
        "windows_edition": "unknown",
        "hyper_v_available": False,
        "sandbox_available": False,
        "sandbox_feature_enabled": False,
        "recommended_mode": "desktop-only",
    }

    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ) as key:
            edition = winreg.QueryValueEx(key, "EditionID")[0]
            result["windows_edition"] = edition
    except Exception:
        pass

    # Check for WindowsSandbox.exe
    sandbox_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
    result["sandbox_available"] = sandbox_exe.exists()

    # Check Hyper-V via registry
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Virtualization",
        ) as key:
            result["hyper_v_available"] = True
    except Exception:
        # Try systeminfo as fallback
        try:
            info = subprocess.run(
                ["systeminfo"],
                capture_output=True, text=True, timeout=15,
            )
            if "Hyper-V" in info.stdout and "Yes" in info.stdout.split("Hyper-V")[-1][:100]:
                result["hyper_v_available"] = True
        except Exception:
            pass

    # Determine recommended mode
    if result["sandbox_available"]:
        result["recommended_mode"] = "sandbox"
        result["sandbox_feature_enabled"] = True
    elif result["hyper_v_available"]:
        result["recommended_mode"] = "time-share"
    else:
        result["recommended_mode"] = "time-share"

    log_action("cv_sandbox_check", {}, "ok")
    return make_success(**result)


# ---------------------------------------------------------------------------
# Batch execution helpers
# ---------------------------------------------------------------------------


def _execute_batch_step(action: BatchAction) -> dict:
    """Execute a single batch step and return the result dict."""
    try:
        if action.action == "click":
            x = action.params.get("x", 0)
            y = action.params.get("y", 0)
            _state.ipc_client.send_request(
                "inject_click", {"x": x, "y": y}, timeout=_BATCH_STEP_TIMEOUT_S
            )
            return {"action": "click", "result": "ok", "params": {"x": x, "y": y}}

        elif action.action == "type":
            text = action.params.get("text", "")
            _state.ipc_client.send_request(
                "inject_keys", {"text": text}, timeout=_BATCH_STEP_TIMEOUT_S
            )
            return {"action": "type", "result": "ok", "params": {"text_len": len(text)}}

        elif action.action == "screenshot":
            result = _state.ipc_client.send_request(
                "capture_frame", {"format": "png"}, timeout=10.0
            )
            data_b64 = result.get("data_b64", "")
            if data_b64:
                png_data = base64.b64decode(data_b64)
                path = _save_screenshot_to_temp(png_data)
                return {"action": "screenshot", "result": "ok", "image_path": path}
            return {"action": "screenshot", "result": "empty_frame"}

        elif action.action == "scene":
            result = _state.ipc_client.send_request(
                "get_scene_graph", timeout=_BATCH_STEP_TIMEOUT_S
            )
            return {"action": "scene", "result": "ok", "element_count": len(result.get("windows", []))}

        else:
            return {"action": action.action, "result": "unknown_action"}

    except Exception as exc:
        return {"action": action.action, "result": f"error: {exc}"}


def _check_assertion(step_result: dict, assert_field: dict) -> bool:
    """Check if a step result matches the assertion criteria."""
    for key, expected in assert_field.items():
        actual = step_result.get(key)
        if actual != expected:
            return False
    return True
