"""Thread-safe LRU element cache for UI Automation metadata.

Caches element metadata (not raw COM pointers) keyed by (hwnd, runtime_id).
On cache hit the caller re-acquires the live COM element on its own thread
via CreatePropertyCondition + FindFirst.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

import win32gui

from src import config
from src.utils.uia import UIA_RUNTIME_ID_PROPERTY_ID

# Limits
MAX_ELEMENTS_PER_WINDOW = 500
MAX_WINDOWS = 50


class CacheHit:
    """Wrapper returned on a successful cache get()."""

    __slots__ = ("metadata", "element")

    def __init__(self, metadata: dict, element: Any) -> None:
        self.metadata = metadata
        self.element = element


class ElementCache:
    """Per-window LRU cache of UI Automation element metadata.

    Keys are (hwnd, tuple(runtime_id)).
    Values are dicts with: name, control_type, rect, is_enabled, ref_id,
    supported_patterns, runtime_id, timestamp.
    """

    def __init__(self, uia_instance: Any | None = None) -> None:
        self._lock = threading.Lock()
        # OrderedDict of hwnd -> OrderedDict[(hwnd, tuple(rid)) -> metadata]
        self._windows: OrderedDict[int, OrderedDict[tuple, dict]] = OrderedDict()
        # ref_id -> (hwnd, tuple(rid)) reverse index
        self._ref_index: dict[str, tuple[int, tuple]] = {}
        # Stats
        self._hits = 0
        self._misses = 0
        # UIA instance for re-acquiring COM elements
        self._uia = uia_instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_hwnd_valid(self, hwnd: int) -> bool:
        """Check if the HWND still maps to a live window (detects recycling)."""
        try:
            return bool(win32gui.IsWindow(hwnd))
        except Exception:
            return False

    def _evict_lru_window(self) -> None:
        """Remove the least-recently-accessed window (must hold lock)."""
        if self._windows:
            oldest_hwnd, oldest_entries = self._windows.popitem(last=False)
            for key, meta in oldest_entries.items():
                self._ref_index.pop(meta.get("ref_id", ""), None)

    def _evict_lru_element(self, window_cache: OrderedDict) -> None:
        """Remove the least-recently-accessed element in a window (must hold lock)."""
        if window_cache:
            _, meta = window_cache.popitem(last=False)
            self._ref_index.pop(meta.get("ref_id", ""), None)

    def _touch_window(self, hwnd: int) -> None:
        """Move window to most-recently-used position (must hold lock)."""
        if hwnd in self._windows:
            self._windows.move_to_end(hwnd)

    def _reacquire_element(self, hwnd: int, runtime_id: tuple) -> Any | None:
        """Re-acquire a live COM element by runtime ID.

        Returns the IUIAutomationElement or None.
        """
        if self._uia is None:
            return None
        try:
            rid_array = list(runtime_id)
            condition = self._uia.CreatePropertyCondition(
                UIA_RUNTIME_ID_PROPERTY_ID, rid_array
            )
            root = self._uia.ElementFromHandle(hwnd)
            # TreeScope_Descendants = 4
            element = root.FindFirst(4, condition)
            return element
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, hwnd: int, ref_id: str) -> CacheHit | None:
        """Look up cached metadata by ref_id, re-acquire live COM element.

        Returns CacheHit(metadata, element) or None on miss / expired / stale hwnd.
        """
        with self._lock:
            # Reverse-index lookup
            key_info = self._ref_index.get(ref_id)
            if key_info is None:
                self._misses += 1
                return None

            cached_hwnd, rid_tuple = key_info

            # Ensure ref_id belongs to expected hwnd
            if cached_hwnd != hwnd:
                self._misses += 1
                return None

            # HWND recycling check
            if not self._is_hwnd_valid(hwnd):
                self._invalidate_window_locked(hwnd)
                self._misses += 1
                return None

            window_cache = self._windows.get(hwnd)
            if window_cache is None:
                self._misses += 1
                return None

            cache_key = (hwnd, rid_tuple)
            meta = window_cache.get(cache_key)
            if meta is None:
                self._misses += 1
                return None

            # TTL check
            if time.monotonic() - meta["_timestamp"] > config.ELEMENT_CACHE_TTL:
                # Expired — remove entry
                del window_cache[cache_key]
                self._ref_index.pop(ref_id, None)
                if not window_cache:
                    self._windows.pop(hwnd, None)
                self._misses += 1
                return None

            # Touch for LRU (element within window, and window itself)
            window_cache.move_to_end(cache_key)
            self._touch_window(hwnd)

            # Copy metadata before releasing lock
            metadata = {k: v for k, v in meta.items() if not k.startswith("_")}
            rid = meta["runtime_id"]

        # Re-acquire COM element outside the lock
        element = self._reacquire_element(hwnd, tuple(rid) if not isinstance(rid, tuple) else rid)
        if element is None:
            # Element no longer in tree — invalidate
            with self._lock:
                self._misses += 1
                wc = self._windows.get(hwnd)
                if wc is not None:
                    wc.pop((hwnd, rid_tuple), None)
                self._ref_index.pop(ref_id, None)
            return None

        with self._lock:
            self._hits += 1

        return CacheHit(metadata=metadata, element=element)

    def put(self, hwnd: int, elements: list[dict]) -> None:
        """Bulk insert element metadata from a tree walk.

        Each dict must contain: name, control_type, rect, is_enabled, ref_id,
        supported_patterns, runtime_id.
        """
        now = time.monotonic()
        with self._lock:
            # Ensure window slot exists
            if hwnd not in self._windows:
                # Evict oldest window if at capacity
                if len(self._windows) >= MAX_WINDOWS:
                    self._evict_lru_window()
                self._windows[hwnd] = OrderedDict()

            window_cache = self._windows[hwnd]
            self._touch_window(hwnd)

            for meta in elements:
                rid = meta.get("runtime_id")
                if rid is None:
                    continue
                rid_tuple = tuple(rid) if not isinstance(rid, tuple) else rid
                cache_key = (hwnd, rid_tuple)

                # Evict oldest element if at per-window capacity
                if cache_key not in window_cache and len(window_cache) >= MAX_ELEMENTS_PER_WINDOW:
                    self._evict_lru_element(window_cache)

                stored = dict(meta)
                stored["_timestamp"] = now
                window_cache[cache_key] = stored
                window_cache.move_to_end(cache_key)

                # Update reverse index
                ref_id = meta.get("ref_id")
                if ref_id:
                    self._ref_index[ref_id] = (hwnd, rid_tuple)

    def invalidate(self, hwnd: int, runtime_id: tuple | list | None = None) -> None:
        """Invalidate a specific element or all elements for a window."""
        with self._lock:
            if runtime_id is None:
                self._invalidate_window_locked(hwnd)
            else:
                rid_tuple = tuple(runtime_id) if not isinstance(runtime_id, tuple) else runtime_id
                wc = self._windows.get(hwnd)
                if wc is not None:
                    cache_key = (hwnd, rid_tuple)
                    meta = wc.pop(cache_key, None)
                    if meta is not None:
                        self._ref_index.pop(meta.get("ref_id", ""), None)
                    if not wc:
                        self._windows.pop(hwnd, None)

    def invalidate_window(self, hwnd: int) -> None:
        """Flush all cached entries for a window."""
        with self._lock:
            self._invalidate_window_locked(hwnd)

    def _invalidate_window_locked(self, hwnd: int) -> None:
        """Internal: invalidate all entries for a window (must hold lock)."""
        wc = self._windows.pop(hwnd, None)
        if wc is not None:
            for _, meta in wc.items():
                self._ref_index.pop(meta.get("ref_id", ""), None)

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total_elements = sum(len(wc) for wc in self._windows.values())
            return {
                "windows": len(self._windows),
                "elements": total_elements,
                "hits": self._hits,
                "misses": self._misses,
            }

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._windows.clear()
            self._ref_index.clear()
            self._hits = 0
            self._misses = 0


# ---------------------------------------------------------------------------
# Module-level singleton with EventManager wiring
# ---------------------------------------------------------------------------

_singleton: ElementCache | None = None
_singleton_lock = threading.Lock()


def get_element_cache() -> ElementCache:
    """Return the shared ElementCache singleton, wired to EventManager."""
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        cache = ElementCache()
        # Wire event-driven invalidation
        try:
            from src.utils.events import get_event_manager
            get_event_manager().set_cache(cache)
        except Exception:
            pass  # Events module not available — degrade gracefully
        _singleton = cache
    return _singleton
