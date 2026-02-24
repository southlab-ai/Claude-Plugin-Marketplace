"""Unit tests for DPI utilities in src/dpi.py."""

from __future__ import annotations

import pytest

from src.dpi import physical_to_logical, logical_to_physical, get_scale_factor


class TestPhysicalToLogical:
    """Tests for physical_to_logical conversion."""

    def test_96dpi_no_scaling(self):
        lx, ly = physical_to_logical(1920, 1080, 96)
        assert lx == 1920
        assert ly == 1080

    def test_144dpi_150_percent(self):
        lx, ly = physical_to_logical(1920, 1080, 144)
        assert lx == 1280
        assert ly == 720

    def test_192dpi_200_percent(self):
        lx, ly = physical_to_logical(1920, 1080, 192)
        assert lx == 960
        assert ly == 540

    def test_origin(self):
        lx, ly = physical_to_logical(0, 0, 144)
        assert lx == 0
        assert ly == 0

    def test_negative_coordinates(self):
        lx, ly = physical_to_logical(-1920, -1080, 144)
        assert lx == -1280
        assert ly == -720

    def test_odd_dpi(self):
        # 120 DPI = 125% scale
        lx, ly = physical_to_logical(1000, 500, 120)
        # 1000 / 1.25 = 800, 500 / 1.25 = 400
        assert lx == 800
        assert ly == 400


class TestLogicalToPhysical:
    """Tests for logical_to_physical conversion."""

    def test_96dpi_no_scaling(self):
        px, py = logical_to_physical(1920, 1080, 96)
        assert px == 1920
        assert py == 1080

    def test_144dpi_150_percent(self):
        px, py = logical_to_physical(1280, 720, 144)
        assert px == 1920
        assert py == 1080

    def test_192dpi_200_percent(self):
        px, py = logical_to_physical(960, 540, 192)
        assert px == 1920
        assert py == 1080

    def test_origin(self):
        px, py = logical_to_physical(0, 0, 144)
        assert px == 0
        assert py == 0

    def test_negative_coordinates(self):
        px, py = logical_to_physical(-1280, -720, 144)
        assert px == -1920
        assert py == -1080

    def test_round_trip_96(self):
        px, py = logical_to_physical(*physical_to_logical(1000, 500, 96), 96)
        assert px == 1000
        assert py == 500

    def test_round_trip_144(self):
        px, py = logical_to_physical(*physical_to_logical(1920, 1080, 144), 144)
        assert px == 1920
        assert py == 1080


class TestGetScaleFactor:
    """Tests for get_scale_factor."""

    def test_96dpi(self):
        assert get_scale_factor(96) == 1.0

    def test_120dpi(self):
        assert get_scale_factor(120) == 1.25

    def test_144dpi(self):
        assert get_scale_factor(144) == 1.5

    def test_168dpi(self):
        assert get_scale_factor(168) == 1.75

    def test_192dpi(self):
        assert get_scale_factor(192) == 2.0

    def test_288dpi(self):
        assert get_scale_factor(288) == 3.0
