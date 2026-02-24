"""Shared test fixtures for the CV plugin test suite."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from src.models import Rect, WindowInfo, MonitorInfo


@pytest.fixture
def mock_hwnd() -> int:
    """A fake window handle for testing."""
    return 12345


@pytest.fixture
def mock_window_info(mock_hwnd: int) -> WindowInfo:
    """A sample WindowInfo for testing."""
    return WindowInfo(
        hwnd=mock_hwnd,
        title="Test Window",
        process_name="test.exe",
        class_name="TestClass",
        pid=9999,
        rect=Rect(x=100, y=100, width=800, height=600),
        monitor_index=0,
        is_minimized=False,
        is_maximized=False,
        is_foreground=True,
    )


@pytest.fixture
def mock_monitor_info() -> MonitorInfo:
    """A sample MonitorInfo for testing."""
    return MonitorInfo(
        index=0,
        name="DISPLAY1",
        rect=Rect(x=0, y=0, width=1920, height=1080),
        work_area=Rect(x=0, y=40, width=1920, height=1040),
        dpi=96,
        scale_factor=1.0,
        is_primary=True,
    )


@pytest.fixture
def mock_monitor_list(mock_monitor_info: MonitorInfo) -> list[MonitorInfo]:
    """A list of MonitorInfo for multi-monitor testing."""
    secondary = MonitorInfo(
        index=1,
        name="DISPLAY2",
        rect=Rect(x=1920, y=0, width=2560, height=1440),
        work_area=Rect(x=1920, y=40, width=2560, height=1400),
        dpi=144,
        scale_factor=1.5,
        is_primary=False,
    )
    return [mock_monitor_info, secondary]


@pytest.fixture
def sample_image() -> Image.Image:
    """A small test image for screenshot testing."""
    return Image.new("RGB", (200, 150), color=(128, 128, 128))


@pytest.fixture
def large_image() -> Image.Image:
    """A large test image that needs downscaling."""
    return Image.new("RGB", (3840, 2160), color=(64, 64, 64))
