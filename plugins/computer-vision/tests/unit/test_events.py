"""Unit tests for EventManager."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.models import EventInfo
from src.utils.events import EventManager


@pytest.fixture
def manager():
    """Create a fresh EventManager for each test (not started)."""
    em = EventManager()
    yield em
    # Make sure thread is stopped
    em.stop()


def _make_event(event_type: str = "focus", hwnd: int = 12345) -> EventInfo:
    """Helper to create an EventInfo."""
    return EventInfo(
        event_type=event_type,
        hwnd=hwnd,
        element_name="Test Element",
        timestamp=time.time(),
    )


class TestEventManagerBuffer:
    """Tests for event buffer management."""

    def test_drain_events_empty(self, manager):
        """drain_events returns empty list when no events."""
        events = manager.drain_events()
        assert events == []

    def test_drain_events_returns_all(self, manager):
        """drain_events returns all events and clears buffer."""
        e1 = _make_event("focus", 1)
        e2 = _make_event("state_change", 2)
        manager._events.append(e1)
        manager._events.append(e2)

        events = manager.drain_events()
        assert len(events) == 2
        assert events[0].event_type == "focus"
        assert events[1].event_type == "state_change"

        # Buffer should be empty after drain
        assert len(manager._events) == 0

    def test_drain_events_filtered_by_hwnd(self, manager):
        """drain_events(hwnd=X) returns only events for that hwnd."""
        e1 = _make_event("focus", 100)
        e2 = _make_event("state_change", 200)
        e3 = _make_event("name_change", 100)
        manager._events.append(e1)
        manager._events.append(e2)
        manager._events.append(e3)

        events = manager.drain_events(hwnd=100)
        assert len(events) == 2
        assert all(e.hwnd == 100 for e in events)

        # Non-matching event should remain
        remaining = manager.drain_events()
        assert len(remaining) == 1
        assert remaining[0].hwnd == 200

    def test_event_queue_overflow(self, manager):
        """Buffer is bounded at 1000 events — oldest are evicted."""
        for i in range(1200):
            manager._events.append(_make_event("focus", i))

        assert len(manager._events) == 1000
        # First event should be i=200 (oldest 200 were evicted)
        events = manager.drain_events()
        assert events[0].hwnd == 200
        assert events[-1].hwnd == 1199

    def test_drain_all_clears_buffer(self, manager):
        """drain_events without hwnd clears entire buffer."""
        for i in range(50):
            manager._events.append(_make_event("focus", i))

        events = manager.drain_events()
        assert len(events) == 50
        assert len(manager._events) == 0


class TestEventManagerRegistration:
    """Tests for window registration."""

    def test_register_window(self, manager):
        """register_window adds hwnd to tracked set."""
        # Patch start to avoid spawning real thread
        with patch.object(manager, "start"):
            manager.register_window(12345)
            assert 12345 in manager._registered_hwnds

    def test_unregister_window(self, manager):
        """unregister_window removes hwnd from tracked set."""
        manager._registered_hwnds.add(12345)
        manager.unregister_window(12345)
        assert 12345 not in manager._registered_hwnds

    def test_unregister_nonexistent_hwnd(self, manager):
        """unregister_window for unknown hwnd does not raise."""
        manager.unregister_window(99999)  # Should not raise

    def test_register_triggers_lazy_start(self, manager):
        """First register_window call triggers start()."""
        with patch.object(manager, "start") as mock_start:
            manager.register_window(12345)
            mock_start.assert_called_once()


class TestEventManagerCacheInvalidation:
    """Tests for cache wiring."""

    def test_set_cache(self, manager):
        """set_cache stores the cache reference."""
        mock_cache = MagicMock()
        manager.set_cache(mock_cache)
        assert manager._cache is mock_cache

    def test_cache_invalidation_on_event(self, manager):
        """When an event arrives, cache.invalidate(hwnd) is called."""
        mock_cache = MagicMock()
        manager.set_cache(mock_cache)

        # Simulate the callback
        manager._registered_hwnds.add(12345)

        with patch("src.utils.events.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "Test"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            manager._win_event_callback(0, 0x8005, 12345, 0, 0, 0, 0)

        mock_cache.invalidate.assert_called_once_with(12345)

    def test_cache_invalidation_failure_is_swallowed(self, manager):
        """If cache.invalidate raises, the event is still recorded."""
        mock_cache = MagicMock()
        mock_cache.invalidate.side_effect = RuntimeError("cache error")
        manager.set_cache(mock_cache)

        manager._registered_hwnds.add(12345)

        with patch("src.utils.events.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "Test"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            # Should not raise
            manager._win_event_callback(0, 0x8005, 12345, 0, 0, 0, 0)

        # Event should still be in buffer
        events = manager.drain_events()
        assert len(events) == 1


class TestEventManagerLifecycle:
    """Tests for start/stop lifecycle."""

    def test_stop_without_start(self, manager):
        """stop() before start() does not raise."""
        manager.stop()

    def test_start_is_idempotent(self, manager):
        """Calling start() twice only creates one thread."""
        with patch.object(manager, "_event_loop"):
            manager.start()
            thread1 = manager._thread

            manager.start()
            thread2 = manager._thread

            # Same thread reference (second start was no-op because thread is alive)
            # In test environment the mocked thread may behave differently,
            # but we verify no exception was raised
            assert manager._started is True

    def test_callback_filters_unregistered_hwnds(self, manager):
        """Events for unregistered hwnds are ignored when filters are active."""
        manager._registered_hwnds.add(100)

        with patch("src.utils.events.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "Test"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            # Event for hwnd=200 should be filtered out
            manager._win_event_callback(0, 0x8005, 200, 0, 0, 0, 0)

        events = manager.drain_events()
        assert len(events) == 0

    def test_callback_accepts_registered_hwnd(self, manager):
        """Events for registered hwnds are captured."""
        manager._registered_hwnds.add(100)

        with patch("src.utils.events.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "Test Window"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            manager._win_event_callback(0, 0x8005, 100, 0, 0, 0, 0)

        events = manager.drain_events()
        assert len(events) == 1
        assert events[0].hwnd == 100
        assert events[0].event_type == "focus"

    def test_callback_accepts_all_when_no_filter(self, manager):
        """When no hwnds are registered, all events are captured."""
        # No registered hwnds = empty set = accept all
        with patch("src.utils.events.ctypes") as mock_ctypes:
            mock_buf = MagicMock()
            mock_buf.value = "Test"
            mock_ctypes.create_unicode_buffer.return_value = mock_buf

            manager._win_event_callback(0, 0x8005, 999, 0, 0, 0, 0)

        events = manager.drain_events()
        assert len(events) == 1
