"""Pydantic models and client for the sandbox shim structured scene graph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.sandbox.ipc.shim_ipc_client import ShimIPCClient

logger = logging.getLogger(__name__)


class ShimRect(BaseModel):
    """Rectangle in window coordinates."""

    x: int
    y: int
    w: int
    h: int


class TextElement(BaseModel):
    """A single text element captured by a render hook."""

    text: str
    font: str = ""
    rect: ShimRect
    hwnd: int
    source_api: str = "gdi"  # "gdi", "dwrite", "dxgi_ocr"
    timestamp_ms: int = 0


class WindowNode(BaseModel):
    """A single window in the shadow tree."""

    hwnd: int
    class_name: str = ""
    title: str = ""
    rect: ShimRect
    parent_hwnd: int = 0
    children_hwnds: list[int] = Field(default_factory=list)
    visible: bool = True
    z_order: int = 0
    styles: int = 0


class FrameCapture(BaseModel):
    """A captured DXGI frame."""

    width: int
    height: int
    format: str = "bgra"
    data_b64: str = ""
    timestamp_ms: int = 0


class SceneGraphSnapshot(BaseModel):
    """Full scene graph snapshot from the shim DLL."""

    version: int = 0
    timestamp_ms: int = 0
    stale: bool = False
    windows: list[WindowNode] = Field(default_factory=list)
    text_elements: list[TextElement] = Field(default_factory=list)
    frame_capture: FrameCapture | None = None


class SceneGraphDiff(BaseModel):
    """Diff since a previous scene graph version."""

    from_version: int
    to_version: int
    timestamp_ms: int = 0
    added_windows: list[WindowNode] = Field(default_factory=list)
    removed_hwnds: list[int] = Field(default_factory=list)
    updated_windows: list[WindowNode] = Field(default_factory=list)
    added_text: list[TextElement] = Field(default_factory=list)
    cleared_text_hwnds: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scene graph IPC client
# ---------------------------------------------------------------------------


class SceneGraphClient:
    """High-level client for querying the scene graph over IPC.

    Wraps a ShimIPCClient and provides typed methods that return
    Pydantic models instead of raw dicts.
    """

    def __init__(self, ipc_client: ShimIPCClient) -> None:
        self._ipc = ipc_client
        self._last_version: int = 0

    @property
    def last_version(self) -> int:
        """The version number of the most recently fetched snapshot."""
        return self._last_version

    def get_current_frame(self) -> SceneGraphSnapshot:
        """Fetch a full scene graph snapshot from the shim.

        Returns:
            A validated SceneGraphSnapshot.

        Raises:
            ConnectionError: If the IPC client is not connected.
            RuntimeError: If the shim returns an error.
        """
        result = self._ipc.send_request("get_scene_graph")
        snapshot = SceneGraphSnapshot.model_validate(result)

        if snapshot.stale:
            logger.warning(
                "Scene graph snapshot v%d is stale (timestamp_ms=%d)",
                snapshot.version,
                snapshot.timestamp_ms,
            )

        self._last_version = snapshot.version
        return snapshot

    def get_diff(self, since_version: int | None = None) -> SceneGraphDiff:
        """Fetch a diff since a previous scene graph version.

        Args:
            since_version: The version to diff from. Defaults to the last
                           version fetched by this client.

        Returns:
            A validated SceneGraphDiff.

        Raises:
            ConnectionError: If the IPC client is not connected.
            RuntimeError: If the shim returns an error.
        """
        base = since_version if since_version is not None else self._last_version
        result = self._ipc.send_request(
            "get_scene_graph", {"since_version": base}
        )
        diff = SceneGraphDiff.model_validate(result)
        self._last_version = diff.to_version
        return diff
