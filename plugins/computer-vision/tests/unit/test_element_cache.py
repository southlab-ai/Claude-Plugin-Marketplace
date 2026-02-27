"""Unit tests for ElementCache — LRU eviction, TTL expiry, HWND recycling,
concurrent access, and invalidation.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from unittest.mock import MagicMock, patch

import pytest

from src.utils.element_cache import (
    CacheHit,
    ElementCache,
    MAX_ELEMENTS_PER_WINDOW,
    MAX_WINDOWS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(ref_id: str, runtime_id: list[int], name: str = "Btn") -> dict:
    """Create a minimal element metadata dict."""
    return {
        "name": name,
        "control_type": "Button",
        "rect": {"x": 10, "y": 20, "width": 80, "height": 30},
        "is_enabled": True,
        "ref_id": ref_id,
        "supported_patterns": ["InvokePattern"],
        "runtime_id": runtime_id,
    }


def _make_uia_mock() -> MagicMock:
    """Return a mock UIA instance whose FindFirst returns a fake element."""
    uia = MagicMock()
    fake_element = MagicMock(name="FakeElement")
    root = MagicMock(name="RootElement")
    root.FindFirst.return_value = fake_element
    uia.ElementFromHandle.return_value = root
    uia.CreatePropertyCondition.return_value = MagicMock(name="Condition")
    return uia


# ---------------------------------------------------------------------------
# Basic put / get
# ---------------------------------------------------------------------------

class TestBasicPutGet:
    def test_put_and_get_hit(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])
            hit = cache.get(100, "ref_1")

        assert hit is not None
        assert isinstance(hit, CacheHit)
        assert hit.metadata["ref_id"] == "ref_1"
        assert hit.element is not None

    def test_miss_returns_none(self):
        cache = ElementCache()
        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            assert cache.get(100, "ref_999") is None

    def test_wrong_hwnd_returns_none(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])
            # Ask for same ref_id but different hwnd
            hit = cache.get(200, "ref_1")

        assert hit is None

    def test_bulk_insert_multiple(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        metas = [_make_meta(f"ref_{i}", [i, 0]) for i in range(10)]

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, metas)
            for i in range(10):
                hit = cache.get(100, f"ref_{i}")
                assert hit is not None

    def test_no_runtime_id_skipped(self):
        cache = ElementCache()
        meta = {"name": "X", "ref_id": "ref_1", "runtime_id": None}
        cache.put(100, [meta])
        s = cache.stats()
        assert s["elements"] == 0


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

class TestTTLExpiry:
    def test_expired_entry_returns_none(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])

            # Artificially expire the entry
            wc = cache._windows[100]
            for key in wc:
                wc[key]["_timestamp"] -= 100  # push back well past TTL

            hit = cache.get(100, "ref_1")

        assert hit is None

    def test_fresh_entry_not_expired(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])
            hit = cache.get(100, "ref_1")

        assert hit is not None


# ---------------------------------------------------------------------------
# HWND recycling
# ---------------------------------------------------------------------------

class TestHWNDRecycling:
    def test_stale_hwnd_invalidated(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])

        # Now HWND is stale
        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=False):
            hit = cache.get(100, "ref_1")

        assert hit is None
        # Window should be evicted
        assert 100 not in cache._windows

    def test_valid_hwnd_keeps_entries(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        meta = _make_meta("ref_1", [1, 2, 3])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.put(100, [meta])
            hit = cache.get(100, "ref_1")

        assert hit is not None
        assert 100 in cache._windows


# ---------------------------------------------------------------------------
# LRU eviction — per window elements
# ---------------------------------------------------------------------------

class TestLRUEvictionElements:
    def test_element_eviction_at_capacity(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)

        # Fill to max capacity
        metas = [_make_meta(f"ref_{i}", [i]) for i in range(MAX_ELEMENTS_PER_WINDOW)]
        cache.put(100, metas)

        assert len(cache._windows[100]) == MAX_ELEMENTS_PER_WINDOW

        # Insert one more — the LRU element should be evicted
        extra = _make_meta("ref_new", [9999])
        cache.put(100, [extra])

        assert len(cache._windows[100]) == MAX_ELEMENTS_PER_WINDOW
        # The first one (ref_0) was LRU and should have been evicted
        assert "ref_0" not in cache._ref_index

    def test_accessing_element_prevents_eviction(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)

        metas = [_make_meta(f"ref_{i}", [i]) for i in range(MAX_ELEMENTS_PER_WINDOW)]
        cache.put(100, metas)

        # Access ref_0 to make it most-recently-used
        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.get(100, "ref_0")

        # Now insert one more — ref_1 (not ref_0) should be evicted
        extra = _make_meta("ref_new", [9999])
        cache.put(100, [extra])

        assert "ref_0" in cache._ref_index
        assert "ref_1" not in cache._ref_index


# ---------------------------------------------------------------------------
# LRU eviction — windows
# ---------------------------------------------------------------------------

class TestLRUEvictionWindows:
    def test_window_eviction_at_capacity(self):
        cache = ElementCache()

        # Fill MAX_WINDOWS
        for hwnd in range(MAX_WINDOWS):
            meta = _make_meta(f"ref_w{hwnd}", [hwnd])
            cache.put(hwnd + 1, [meta])

        assert len(cache._windows) == MAX_WINDOWS

        # Insert one more window
        meta = _make_meta("ref_extra", [999])
        cache.put(9999, [meta])

        assert len(cache._windows) == MAX_WINDOWS
        # First window (hwnd=1) should have been evicted
        assert 1 not in cache._windows

    def test_accessing_window_prevents_eviction(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)

        for hwnd in range(MAX_WINDOWS):
            meta = _make_meta(f"ref_w{hwnd}", [hwnd])
            cache.put(hwnd + 1, [meta])

        # Access hwnd=1 to make it MRU
        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.get(1, "ref_w0")

        # Add one more window
        meta = _make_meta("ref_extra", [999])
        cache.put(9999, [meta])

        # hwnd=1 should survive, hwnd=2 (now LRU) should be evicted
        assert 1 in cache._windows
        assert 2 not in cache._windows


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

class TestInvalidation:
    def test_invalidate_specific_element(self):
        cache = ElementCache()
        metas = [
            _make_meta("ref_1", [1]),
            _make_meta("ref_2", [2]),
        ]
        cache.put(100, metas)

        cache.invalidate(100, runtime_id=[1])
        assert "ref_1" not in cache._ref_index
        assert "ref_2" in cache._ref_index

    def test_invalidate_all_for_window(self):
        cache = ElementCache()
        metas = [_make_meta(f"ref_{i}", [i]) for i in range(5)]
        cache.put(100, metas)

        cache.invalidate(100)
        assert 100 not in cache._windows
        for i in range(5):
            assert f"ref_{i}" not in cache._ref_index

    def test_invalidate_window_method(self):
        cache = ElementCache()
        metas = [_make_meta("ref_1", [1])]
        cache.put(100, metas)

        cache.invalidate_window(100)
        assert 100 not in cache._windows
        assert cache._ref_index == {}

    def test_invalidate_nonexistent_is_noop(self):
        cache = ElementCache()
        # Should not raise
        cache.invalidate(999)
        cache.invalidate(999, runtime_id=[1, 2])
        cache.invalidate_window(999)


# ---------------------------------------------------------------------------
# Stats and clear
# ---------------------------------------------------------------------------

class TestStatsAndClear:
    def test_stats_empty(self):
        cache = ElementCache()
        s = cache.stats()
        assert s == {"windows": 0, "elements": 0, "hits": 0, "misses": 0}

    def test_stats_after_operations(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        metas = [_make_meta(f"ref_{i}", [i]) for i in range(3)]
        cache.put(100, metas)

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            cache.get(100, "ref_0")  # hit
            cache.get(100, "ref_999")  # miss

        s = cache.stats()
        assert s["windows"] == 1
        assert s["elements"] == 3
        assert s["hits"] == 1
        assert s["misses"] == 1

    def test_clear(self):
        cache = ElementCache()
        cache.put(100, [_make_meta("ref_1", [1])])
        cache.clear()
        s = cache.stats()
        assert s == {"windows": 0, "elements": 0, "hits": 0, "misses": 0}


# ---------------------------------------------------------------------------
# Re-acquire failure
# ---------------------------------------------------------------------------

class TestReacquireFailure:
    def test_reacquire_returns_none_removes_entry(self):
        uia = MagicMock()
        root = MagicMock()
        root.FindFirst.return_value = None  # element gone
        uia.ElementFromHandle.return_value = root
        uia.CreatePropertyCondition.return_value = MagicMock()

        cache = ElementCache(uia_instance=uia)
        cache.put(100, [_make_meta("ref_1", [1, 2])])

        with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
            hit = cache.get(100, "ref_1")

        assert hit is None
        # Entry should have been removed
        assert "ref_1" not in cache._ref_index


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------

class TestConcurrentAccess:
    def test_concurrent_put_and_get(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        errors: list[Exception] = []

        def _writer(start: int) -> None:
            try:
                for i in range(50):
                    idx = start + i
                    cache.put(100, [_make_meta(f"ref_t{idx}", [idx])])
            except Exception as e:
                errors.append(e)

        def _reader() -> None:
            try:
                with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
                    for i in range(50):
                        cache.get(100, f"ref_t{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(0,)),
            threading.Thread(target=_writer, args=(1000,)),
            threading.Thread(target=_reader),
            threading.Thread(target=_reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Concurrent access raised: {errors}"

    def test_concurrent_invalidate_and_get(self):
        uia = _make_uia_mock()
        cache = ElementCache(uia_instance=uia)
        metas = [_make_meta(f"ref_{i}", [i]) for i in range(100)]
        cache.put(100, metas)
        errors: list[Exception] = []

        def _invalidator() -> None:
            try:
                for i in range(100):
                    cache.invalidate(100, runtime_id=[i])
            except Exception as e:
                errors.append(e)

        def _reader() -> None:
            try:
                with patch("src.utils.element_cache.win32gui.IsWindow", return_value=True):
                    for i in range(100):
                        cache.get(100, f"ref_{i}")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_invalidator)
        t2 = threading.Thread(target=_reader)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert errors == []
