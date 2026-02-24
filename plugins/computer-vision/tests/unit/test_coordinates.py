"""Unit tests for coordinate transformations in src/coordinates.py."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from unittest.mock import patch, MagicMock

import pytest


class TestNormalizeForSendinput:
    """Tests for normalize_for_sendinput."""

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_center_of_single_monitor(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import normalize_for_sendinput

        nx, ny = normalize_for_sendinput(960, 540)
        # Expected: (960 * 65535) / 1919 ~= 32784
        assert 32000 <= nx <= 33500
        assert 32000 <= ny <= 33500

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_origin(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import normalize_for_sendinput

        nx, ny = normalize_for_sendinput(0, 0)
        assert nx == 0
        assert ny == 0

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_bottom_right(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import normalize_for_sendinput

        nx, ny = normalize_for_sendinput(1919, 1079)
        assert nx == 65535
        assert ny == 65535

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_negative_origin(self, mock_bounds):
        # Multi-monitor with left monitor at negative coords
        mock_bounds.return_value = (-1920, 0, 3840, 1080)
        from src.coordinates import normalize_for_sendinput

        # Point at (0, 540) — center of combined desktops horizontally shifted
        nx, ny = normalize_for_sendinput(0, 540)
        assert 0 < nx < 65535
        assert 0 < ny < 65535

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_clamps_to_valid_range(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import normalize_for_sendinput

        # Even if input is out of range, output should clamp to [0, 65535]
        nx, ny = normalize_for_sendinput(-100, -100)
        assert nx >= 0
        assert ny >= 0


class TestToScreenAbsolute:
    """Tests for to_screen_absolute."""

    @patch("src.coordinates.ctypes.windll.user32.ClientToScreen")
    def test_calls_client_to_screen(self, mock_client_to_screen):
        from src.coordinates import to_screen_absolute

        # ClientToScreen modifies the POINT in-place. When mocked, the
        # POINT keeps its initial values (which are the input coords).
        mock_client_to_screen.return_value = True
        result = to_screen_absolute(100, 100, 12345)
        assert isinstance(result, tuple)
        assert len(result) == 2
        # Verify ClientToScreen was called with the hwnd
        mock_client_to_screen.assert_called_once()
        call_args = mock_client_to_screen.call_args
        assert call_args[0][0] == 12345  # hwnd argument


class TestValidateCoordinates:
    """Tests for validate_coordinates."""

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_valid_center(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(960, 540) is True

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_origin_valid(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(0, 0) is True

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_just_outside_right(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(1920, 540) is False

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_just_outside_bottom(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(960, 1080) is False

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_negative_origin_valid(self, mock_bounds):
        mock_bounds.return_value = (-1920, 0, 3840, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(-960, 540) is True

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_far_outside(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(5000, 5000) is False

    @patch("src.coordinates.get_virtual_desktop_bounds")
    def test_negative_coords_no_negative_origin(self, mock_bounds):
        mock_bounds.return_value = (0, 0, 1920, 1080)
        from src.coordinates import validate_coordinates

        assert validate_coordinates(-100, -100) is False
