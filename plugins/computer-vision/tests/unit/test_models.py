"""Unit tests for Pydantic models in src/models.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import Rect, WindowInfo, MonitorInfo, UiaElement


class TestRect:
    """Tests for the Rect model."""

    def test_basic_creation(self):
        r = Rect(x=0, y=0, width=100, height=100)
        assert r.x == 0
        assert r.y == 0
        assert r.width == 100
        assert r.height == 100

    def test_negative_coordinates(self):
        r = Rect(x=-500, y=-300, width=1920, height=1080)
        assert r.x == -500
        assert r.y == -300

    def test_zero_dimensions(self):
        r = Rect(x=0, y=0, width=0, height=0)
        assert r.width == 0
        assert r.height == 0

    def test_large_values(self):
        r = Rect(x=0, y=0, width=7680, height=4320)
        assert r.width == 7680

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            Rect(x=0, y=0, width=100)  # missing height

    def test_serialization_round_trip(self):
        r = Rect(x=10, y=20, width=30, height=40)
        data = r.model_dump()
        r2 = Rect(**data)
        assert r == r2


class TestWindowInfo:
    """Tests for the WindowInfo model."""

    def test_basic_creation(self):
        w = WindowInfo(
            hwnd=12345,
            title="Test",
            process_name="notepad",
            class_name="Notepad",
            pid=1000,
            rect=Rect(x=0, y=0, width=800, height=600),
        )
        assert w.hwnd == 12345
        assert w.title == "Test"

    def test_defaults(self):
        w = WindowInfo(
            hwnd=1,
            title="",
            process_name="",
            class_name="",
            pid=0,
            rect=Rect(x=0, y=0, width=0, height=0),
        )
        assert w.monitor_index == 0
        assert w.is_minimized is False
        assert w.is_maximized is False
        assert w.is_foreground is False

    def test_all_flags_true(self):
        w = WindowInfo(
            hwnd=1,
            title="Full",
            process_name="app",
            class_name="App",
            pid=100,
            rect=Rect(x=0, y=0, width=1920, height=1080),
            monitor_index=2,
            is_minimized=True,
            is_maximized=True,
            is_foreground=True,
        )
        assert w.is_minimized is True
        assert w.is_maximized is True
        assert w.is_foreground is True
        assert w.monitor_index == 2

    def test_empty_title(self):
        w = WindowInfo(
            hwnd=1,
            title="",
            process_name="p",
            class_name="c",
            pid=1,
            rect=Rect(x=0, y=0, width=1, height=1),
        )
        assert w.title == ""

    def test_serialization(self):
        w = WindowInfo(
            hwnd=999,
            title="Serialization Test",
            process_name="test",
            class_name="TestClass",
            pid=42,
            rect=Rect(x=10, y=20, width=300, height=200),
        )
        data = w.model_dump()
        assert data["hwnd"] == 999
        assert data["rect"]["x"] == 10


class TestMonitorInfo:
    """Tests for the MonitorInfo model."""

    def test_basic_creation(self):
        m = MonitorInfo(
            index=0,
            name="DISPLAY1",
            rect=Rect(x=0, y=0, width=1920, height=1080),
            work_area=Rect(x=0, y=40, width=1920, height=1040),
            dpi=96,
            scale_factor=1.0,
            is_primary=True,
        )
        assert m.index == 0
        assert m.is_primary is True
        assert m.dpi == 96

    def test_high_dpi_monitor(self):
        m = MonitorInfo(
            index=1,
            name="DISPLAY2",
            rect=Rect(x=1920, y=0, width=3840, height=2160),
            work_area=Rect(x=1920, y=0, width=3840, height=2160),
            dpi=192,
            scale_factor=2.0,
            is_primary=False,
        )
        assert m.scale_factor == 2.0
        assert m.dpi == 192

    def test_negative_origin_monitor(self):
        m = MonitorInfo(
            index=2,
            name="LEFT",
            rect=Rect(x=-1920, y=0, width=1920, height=1080),
            work_area=Rect(x=-1920, y=40, width=1920, height=1040),
            dpi=96,
            scale_factor=1.0,
            is_primary=False,
        )
        assert m.rect.x == -1920


class TestUiaElement:
    """Tests for the UiaElement model."""

    def test_basic_creation(self):
        e = UiaElement(
            ref_id="ref_1",
            name="OK",
            control_type="Button",
            rect=Rect(x=100, y=200, width=80, height=30),
        )
        assert e.ref_id == "ref_1"
        assert e.name == "OK"
        assert e.is_enabled is True
        assert e.is_interactive is False
        assert e.children == []

    def test_with_children(self):
        child = UiaElement(
            ref_id="ref_2",
            name="Child",
            control_type="Text",
            rect=Rect(x=0, y=0, width=50, height=20),
        )
        parent = UiaElement(
            ref_id="ref_1",
            name="Parent",
            control_type="Group",
            rect=Rect(x=0, y=0, width=200, height=100),
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].name == "Child"

    def test_with_value(self):
        e = UiaElement(
            ref_id="ref_1",
            name="Username",
            control_type="Edit",
            rect=Rect(x=0, y=0, width=200, height=25),
            value="john_doe",
        )
        assert e.value == "john_doe"

    def test_none_value_default(self):
        e = UiaElement(
            ref_id="ref_1",
            name="Btn",
            control_type="Button",
            rect=Rect(x=0, y=0, width=80, height=30),
        )
        assert e.value is None

    def test_disabled_element(self):
        e = UiaElement(
            ref_id="ref_1",
            name="Disabled",
            control_type="Button",
            rect=Rect(x=0, y=0, width=80, height=30),
            is_enabled=False,
        )
        assert e.is_enabled is False

    def test_interactive_flag(self):
        e = UiaElement(
            ref_id="ref_1",
            name="Link",
            control_type="Hyperlink",
            rect=Rect(x=0, y=0, width=100, height=20),
            is_interactive=True,
        )
        assert e.is_interactive is True

    def test_deep_nesting(self):
        leaf = UiaElement(
            ref_id="ref_3",
            name="Leaf",
            control_type="Text",
            rect=Rect(x=0, y=0, width=10, height=10),
        )
        mid = UiaElement(
            ref_id="ref_2",
            name="Mid",
            control_type="Group",
            rect=Rect(x=0, y=0, width=50, height=50),
            children=[leaf],
        )
        root = UiaElement(
            ref_id="ref_1",
            name="Root",
            control_type="Pane",
            rect=Rect(x=0, y=0, width=100, height=100),
            children=[mid],
        )
        assert root.children[0].children[0].name == "Leaf"

    def test_serialization(self):
        e = UiaElement(
            ref_id="ref_1",
            name="Test",
            control_type="Button",
            rect=Rect(x=5, y=10, width=80, height=30),
            is_interactive=True,
        )
        data = e.model_dump()
        assert data["ref_id"] == "ref_1"
        assert data["rect"]["x"] == 5
        assert data["is_interactive"] is True
        e2 = UiaElement(**data)
        assert e2 == e
