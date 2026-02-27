"""Tests for the scene graph Pydantic models (src/sandbox/models/scene_graph.py)."""

from __future__ import annotations

import json

import pytest

from src.sandbox.models.scene_graph import (
    FrameCapture,
    SceneGraphDiff,
    SceneGraphSnapshot,
    ShimRect,
    TextElement,
    WindowNode,
)


class TestShimRect:
    """Tests for ShimRect."""

    def test_shim_rect_creation(self) -> None:
        """Basic ShimRect creation with all required fields."""
        rect = ShimRect(x=10, y=20, w=300, h=400)
        assert rect.x == 10
        assert rect.y == 20
        assert rect.w == 300
        assert rect.h == 400

    def test_shim_rect_zero(self) -> None:
        """ShimRect with zero dimensions."""
        rect = ShimRect(x=0, y=0, w=0, h=0)
        assert rect.x == 0
        assert rect.w == 0

    def test_shim_rect_negative(self) -> None:
        """ShimRect with negative coordinates (valid for off-screen windows)."""
        rect = ShimRect(x=-100, y=-50, w=800, h=600)
        assert rect.x == -100
        assert rect.y == -50


class TestTextElement:
    """Tests for TextElement."""

    def test_text_element_defaults(self) -> None:
        """TextElement with minimal args; verify defaults."""
        rect = ShimRect(x=0, y=0, w=100, h=20)
        elem = TextElement(text="Hello", rect=rect, hwnd=1234)
        assert elem.text == "Hello"
        assert elem.font == ""
        assert elem.source_api == "gdi"
        assert elem.timestamp_ms == 0
        assert elem.hwnd == 1234

    def test_text_element_full(self) -> None:
        """TextElement with all fields specified."""
        rect = ShimRect(x=10, y=20, w=200, h=30)
        elem = TextElement(
            text="World",
            font="Segoe UI",
            rect=rect,
            hwnd=5678,
            source_api="dwrite",
            timestamp_ms=999,
        )
        assert elem.text == "World"
        assert elem.font == "Segoe UI"
        assert elem.source_api == "dwrite"
        assert elem.timestamp_ms == 999
        assert elem.rect.x == 10

    def test_text_element_dxgi_ocr_source(self) -> None:
        """TextElement with dxgi_ocr source API."""
        rect = ShimRect(x=0, y=0, w=50, h=12)
        elem = TextElement(text="OCR text", rect=rect, hwnd=1, source_api="dxgi_ocr")
        assert elem.source_api == "dxgi_ocr"


class TestWindowNode:
    """Tests for WindowNode."""

    def test_window_node_with_children(self) -> None:
        """WindowNode with children_hwnds list."""
        rect = ShimRect(x=0, y=0, w=800, h=600)
        node = WindowNode(
            hwnd=100,
            class_name="Notepad",
            title="Untitled - Notepad",
            rect=rect,
            parent_hwnd=0,
            children_hwnds=[200, 201, 202],
            visible=True,
            z_order=1,
            styles=0x10CF0000,
        )
        assert node.hwnd == 100
        assert node.class_name == "Notepad"
        assert node.title == "Untitled - Notepad"
        assert node.children_hwnds == [200, 201, 202]
        assert node.visible is True
        assert node.z_order == 1
        assert node.styles == 0x10CF0000

    def test_window_node_defaults(self) -> None:
        """WindowNode with only required fields; verify defaults."""
        rect = ShimRect(x=0, y=0, w=100, h=100)
        node = WindowNode(hwnd=1, rect=rect)
        assert node.class_name == ""
        assert node.title == ""
        assert node.parent_hwnd == 0
        assert node.children_hwnds == []
        assert node.visible is True
        assert node.z_order == 0
        assert node.styles == 0

    def test_window_node_invisible(self) -> None:
        """WindowNode marked as not visible."""
        rect = ShimRect(x=0, y=0, w=1, h=1)
        node = WindowNode(hwnd=999, rect=rect, visible=False)
        assert node.visible is False


class TestFrameCapture:
    """Tests for FrameCapture."""

    def test_frame_capture_serialization(self) -> None:
        """FrameCapture to dict and back."""
        frame = FrameCapture(
            width=1920,
            height=1080,
            format="bgra",
            data_b64="AAAA",
            timestamp_ms=12345,
        )
        data = frame.model_dump()
        assert data["width"] == 1920
        assert data["height"] == 1080
        assert data["format"] == "bgra"
        assert data["data_b64"] == "AAAA"
        assert data["timestamp_ms"] == 12345

        # Reconstruct from dict
        restored = FrameCapture.model_validate(data)
        assert restored == frame

    def test_frame_capture_defaults(self) -> None:
        """FrameCapture defaults."""
        frame = FrameCapture(width=640, height=480)
        assert frame.format == "bgra"
        assert frame.data_b64 == ""
        assert frame.timestamp_ms == 0


class TestSceneGraphSnapshot:
    """Tests for SceneGraphSnapshot."""

    def test_scene_graph_snapshot_empty(self) -> None:
        """Empty snapshot with defaults."""
        snap = SceneGraphSnapshot()
        assert snap.version == 0
        assert snap.timestamp_ms == 0
        assert snap.stale is False
        assert snap.windows == []
        assert snap.text_elements == []
        assert snap.frame_capture is None

    def test_scene_graph_snapshot_full(self) -> None:
        """Snapshot with windows + text + frame."""
        rect = ShimRect(x=0, y=0, w=800, h=600)
        win = WindowNode(hwnd=100, class_name="MyClass", title="Win", rect=rect)
        txt = TextElement(text="Hello", rect=ShimRect(x=10, y=10, w=50, h=12), hwnd=100)
        frame = FrameCapture(width=800, height=600, data_b64="dGVzdA==")

        snap = SceneGraphSnapshot(
            version=3,
            timestamp_ms=5000,
            stale=False,
            windows=[win],
            text_elements=[txt],
            frame_capture=frame,
        )
        assert snap.version == 3
        assert snap.timestamp_ms == 5000
        assert len(snap.windows) == 1
        assert snap.windows[0].hwnd == 100
        assert len(snap.text_elements) == 1
        assert snap.text_elements[0].text == "Hello"
        assert snap.frame_capture is not None
        assert snap.frame_capture.width == 800

    def test_scene_graph_snapshot_stale(self) -> None:
        """Snapshot with stale=True."""
        snap = SceneGraphSnapshot(stale=True, version=10, timestamp_ms=99999)
        assert snap.stale is True
        assert snap.version == 10


class TestSceneGraphDiff:
    """Tests for SceneGraphDiff."""

    def test_scene_graph_diff(self) -> None:
        """Diff with added/removed/updated."""
        rect = ShimRect(x=0, y=0, w=100, h=100)
        added_win = WindowNode(hwnd=300, rect=rect, title="New")
        updated_win = WindowNode(hwnd=100, rect=rect, title="Updated")
        added_txt = TextElement(text="new text", rect=rect, hwnd=300)

        diff = SceneGraphDiff(
            from_version=1,
            to_version=2,
            timestamp_ms=6000,
            added_windows=[added_win],
            removed_hwnds=[200],
            updated_windows=[updated_win],
            added_text=[added_txt],
            cleared_text_hwnds=[150],
        )
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert diff.timestamp_ms == 6000
        assert len(diff.added_windows) == 1
        assert diff.added_windows[0].hwnd == 300
        assert diff.removed_hwnds == [200]
        assert len(diff.updated_windows) == 1
        assert diff.updated_windows[0].title == "Updated"
        assert len(diff.added_text) == 1
        assert diff.cleared_text_hwnds == [150]

    def test_scene_graph_diff_defaults(self) -> None:
        """Diff with only required fields."""
        diff = SceneGraphDiff(from_version=0, to_version=1)
        assert diff.timestamp_ms == 0
        assert diff.added_windows == []
        assert diff.removed_hwnds == []
        assert diff.updated_windows == []
        assert diff.added_text == []
        assert diff.cleared_text_hwnds == []


class TestJsonRoundTrip:
    """Model -> JSON -> model for all types."""

    def test_json_round_trip_shim_rect(self) -> None:
        original = ShimRect(x=1, y=2, w=3, h=4)
        json_str = original.model_dump_json()
        restored = ShimRect.model_validate_json(json_str)
        assert restored == original

    def test_json_round_trip_text_element(self) -> None:
        rect = ShimRect(x=0, y=0, w=100, h=20)
        original = TextElement(
            text="Test",
            font="Arial",
            rect=rect,
            hwnd=42,
            source_api="dwrite",
            timestamp_ms=500,
        )
        json_str = original.model_dump_json()
        restored = TextElement.model_validate_json(json_str)
        assert restored == original

    def test_json_round_trip_window_node(self) -> None:
        rect = ShimRect(x=50, y=50, w=400, h=300)
        original = WindowNode(
            hwnd=1,
            class_name="Cls",
            title="Title",
            rect=rect,
            parent_hwnd=0,
            children_hwnds=[2, 3],
            visible=True,
            z_order=5,
            styles=0xFF,
        )
        json_str = original.model_dump_json()
        restored = WindowNode.model_validate_json(json_str)
        assert restored == original

    def test_json_round_trip_frame_capture(self) -> None:
        original = FrameCapture(
            width=1920,
            height=1080,
            format="bgra",
            data_b64="QUFB",
            timestamp_ms=100,
        )
        json_str = original.model_dump_json()
        restored = FrameCapture.model_validate_json(json_str)
        assert restored == original

    def test_json_round_trip_snapshot(self) -> None:
        rect = ShimRect(x=0, y=0, w=800, h=600)
        win = WindowNode(hwnd=10, rect=rect, title="W")
        txt = TextElement(text="T", rect=rect, hwnd=10)
        frame = FrameCapture(width=800, height=600)
        original = SceneGraphSnapshot(
            version=7,
            timestamp_ms=9000,
            windows=[win],
            text_elements=[txt],
            frame_capture=frame,
        )
        json_str = original.model_dump_json()
        restored = SceneGraphSnapshot.model_validate_json(json_str)
        assert restored == original

    def test_json_round_trip_diff(self) -> None:
        rect = ShimRect(x=0, y=0, w=50, h=50)
        original = SceneGraphDiff(
            from_version=3,
            to_version=4,
            timestamp_ms=1234,
            added_windows=[WindowNode(hwnd=1, rect=rect)],
            removed_hwnds=[2],
            updated_windows=[],
            added_text=[TextElement(text="x", rect=rect, hwnd=1)],
            cleared_text_hwnds=[3],
        )
        json_str = original.model_dump_json()
        restored = SceneGraphDiff.model_validate_json(json_str)
        assert restored == original
