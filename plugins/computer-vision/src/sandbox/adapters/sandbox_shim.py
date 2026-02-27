"""Sandbox shim adapter — bridges the adapter system to sandbox IPC.

Self-registers with AdapterRegistry at import time for the
"windowssandbox" process pattern.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.adapters import AdapterRegistry, BaseAdapter
from src.models import ActionResult
from src.sandbox.ipc.shim_ipc_client import ShimIPCClient
from src.sandbox.models.scene_graph import SceneGraphClient

logger = logging.getLogger(__name__)

_SUPPORTED_ACTIONS = frozenset({"invoke", "set_value", "get_value", "get_text", "get_scene"})

_STRATEGY = "adapter_sandbox_shim"


class SandboxShimAdapter(BaseAdapter):
    """Adapter that routes actions through the sandbox shim IPC layer.

    Requires an active ShimIPCClient connection. The lifecycle manager
    is responsible for establishing the connection and injecting the DLL;
    this adapter only consumes the already-connected client.
    """

    def __init__(self) -> None:
        self._ipc_client: ShimIPCClient | None = None
        self._scene_client: SceneGraphClient | None = None

    # ------------------------------------------------------------------
    # Client wiring (called by lifecycle manager after connection)
    # ------------------------------------------------------------------

    def set_ipc_client(self, client: ShimIPCClient) -> None:
        """Attach a connected IPC client to this adapter."""
        self._ipc_client = client
        self._scene_client = SceneGraphClient(client)

    # ------------------------------------------------------------------
    # BaseAdapter interface
    # ------------------------------------------------------------------

    def probe(self, hwnd: int) -> bool:
        """Return True if the IPC client is connected and responsive."""
        if self._ipc_client is None or not self._ipc_client.connected:
            return False
        try:
            self._ipc_client.send_request("ping", timeout=1.0)
            return True
        except Exception:
            return False

    def supports_action(self, action: str) -> bool:
        """Return True if *action* is one of the supported sandbox actions."""
        return action in _SUPPORTED_ACTIONS

    def execute(self, hwnd: int, target: str, action: str, value: str | None) -> ActionResult:
        """Execute an action through the sandbox shim.

        Args:
            hwnd: Window handle (used for context, not directly by IPC).
            target: Target selector — coordinates for invoke, text pattern for get_text.
            action: One of the supported action names.
            value: Optional value for set_value.

        Returns:
            ActionResult describing the outcome.
        """
        if self._ipc_client is None or not self._ipc_client.connected:
            return ActionResult(
                success=False,
                strategy_used=_STRATEGY,
                layer=0,
            )

        try:
            if action == "invoke":
                return self._do_invoke(target)
            elif action == "set_value":
                return self._do_set_value(target, value)
            elif action in ("get_value", "get_text"):
                return self._do_get_text(target)
            elif action == "get_scene":
                return self._do_get_scene()
            else:
                return ActionResult(
                    success=False,
                    strategy_used=_STRATEGY,
                    layer=0,
                )
        except Exception as exc:
            logger.error("SandboxShimAdapter.execute(%s) failed: %s", action, exc)
            return ActionResult(
                success=False,
                strategy_used=_STRATEGY,
                layer=0,
            )

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    def _do_invoke(self, target: str) -> ActionResult:
        """Inject a click at the target coordinates.

        Expects *target* to be "x,y" coordinates.
        """
        x, y = _parse_coordinates(target)
        self._ipc_client.send_request("inject_click", {"x": x, "y": y})
        return ActionResult(success=True, strategy_used=_STRATEGY, layer=0)

    def _do_set_value(self, target: str, value: str | None) -> ActionResult:
        """Inject keystrokes to set a value."""
        if value is None:
            return ActionResult(success=False, strategy_used=_STRATEGY, layer=0)
        self._ipc_client.send_request("inject_keys", {"text": value})
        return ActionResult(success=True, strategy_used=_STRATEGY, layer=0)

    def _do_get_text(self, target: str) -> ActionResult:
        """Get text from the scene graph matching the target pattern."""
        if self._scene_client is None:
            return ActionResult(success=False, strategy_used=_STRATEGY, layer=0)

        snapshot = self._scene_client.get_current_frame()
        target_lower = target.lower()

        for elem in snapshot.text_elements:
            if target_lower in elem.text.lower():
                return ActionResult(
                    success=True,
                    strategy_used=_STRATEGY,
                    layer=0,
                    element={"text": elem.text, "rect": elem.rect.model_dump()},
                )

        return ActionResult(
            success=False,
            strategy_used=_STRATEGY,
            layer=0,
        )

    def _do_get_scene(self) -> ActionResult:
        """Return the full scene graph as the element payload."""
        if self._scene_client is None:
            return ActionResult(success=False, strategy_used=_STRATEGY, layer=0)

        snapshot = self._scene_client.get_current_frame()
        return ActionResult(
            success=True,
            strategy_used=_STRATEGY,
            layer=0,
            element=json.loads(snapshot.model_dump_json()),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_coordinates(target: str) -> tuple[int, int]:
    """Parse 'x,y' string into integer coordinates.

    Raises ValueError if the format is invalid.
    """
    parts = target.split(",")
    if len(parts) != 2:
        raise ValueError(f"Expected 'x,y' coordinate format, got: {target!r}")
    return int(parts[0].strip()), int(parts[1].strip())


# ---------------------------------------------------------------------------
# Self-registration at import time
# ---------------------------------------------------------------------------

AdapterRegistry().register(["windowssandbox"], SandboxShimAdapter)
