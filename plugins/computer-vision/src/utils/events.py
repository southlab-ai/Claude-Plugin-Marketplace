"""Event manager for monitoring Windows UI events via WinEventHook and UIA."""

from __future__ import annotations

import collections
import ctypes
import ctypes.wintypes
import logging
import threading
import time
from typing import Any, Callable

from src.models import EventInfo

logger = logging.getLogger(__name__)

# Windows event constants
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_FOCUS = 0x8005
EVENT_OBJECT_STATECHANGE = 0x800A
EVENT_OBJECT_NAMECHANGE = 0x800C

# Event names for human-readable logging
_EVENT_NAMES: dict[int, str] = {
    EVENT_SYSTEM_FOREGROUND: "foreground",
    EVENT_OBJECT_CREATE: "create",
    EVENT_OBJECT_DESTROY: "destroy",
    EVENT_OBJECT_FOCUS: "focus",
    EVENT_OBJECT_STATECHANGE: "state_change",
    EVENT_OBJECT_NAMECHANGE: "name_change",
}

# PeekMessage constants
PM_REMOVE = 0x0001
WM_QUIT = 0x0012

# WinEventHook flags
WINEVENT_OUTOFCONTEXT = 0x0000

# COM initialization
COINIT_MULTITHREADED = 0x0

# ctypes callback type for SetWinEventHook
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    ctypes.wintypes.HANDLE,  # hWinEventHook
    ctypes.wintypes.DWORD,   # event
    ctypes.wintypes.HWND,    # hwnd
    ctypes.c_long,           # idObject
    ctypes.c_long,           # idChild
    ctypes.wintypes.DWORD,   # dwEventThread
    ctypes.wintypes.DWORD,   # dwmsEventTime
)

# Maximum events in the buffer
_MAX_EVENTS = 1000


class EventManager:
    """Manages a dedicated daemon thread for monitoring Windows UI events.

    Uses SetWinEventHook via ctypes to capture focus, state change, name change,
    create, destroy, and foreground events. Events are stored in a bounded deque
    and can be drained by consumers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: collections.deque[EventInfo] = collections.deque(maxlen=_MAX_EVENTS)
        self._registered_hwnds: set[int] = set()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started = False
        self._hooks: list[ctypes.wintypes.HANDLE] = []
        self._cache: Any = None
        # Must keep a reference to the callback to prevent GC
        self._callback_ref: WINEVENTPROC | None = None

    def start(self) -> None:
        """Start the event monitoring daemon thread.

        Creates a daemon thread that initializes COM, installs WinEventHooks,
        and runs a message pump. Safe to call multiple times (idempotent).
        """
        with self._lock:
            if self._started and self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._event_loop, daemon=True, name="cv-event-manager"
            )
            self._started = True
            self._thread.start()

    def stop(self) -> None:
        """Signal the event thread to exit and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        with self._lock:
            self._started = False
            self._hooks.clear()

    def register_window(self, hwnd: int) -> None:
        """Subscribe to events for a specific window.

        Lazily starts the event thread on first registration.
        """
        with self._lock:
            self._registered_hwnds.add(hwnd)
        # Lazy start
        if not self._started:
            self.start()

    def unregister_window(self, hwnd: int) -> None:
        """Unsubscribe from events for a specific window."""
        with self._lock:
            self._registered_hwnds.discard(hwnd)

    def drain_events(self, hwnd: int | None = None) -> list[EventInfo]:
        """Drain and return all buffered events, optionally filtered by hwnd.

        Args:
            hwnd: If provided, only return events for this window handle.
                  Events for other windows remain in the buffer.

        Returns:
            List of EventInfo objects.
        """
        with self._lock:
            if hwnd is None:
                # Drain all events
                events = list(self._events)
                self._events.clear()
                return events
            else:
                # Filter by hwnd — keep non-matching events in the buffer
                matching = []
                remaining: collections.deque[EventInfo] = collections.deque(maxlen=_MAX_EVENTS)
                for event in self._events:
                    if event.hwnd == hwnd:
                        matching.append(event)
                    else:
                        remaining.append(event)
                self._events = remaining
                return matching

    def set_cache(self, cache: Any) -> None:
        """Wire a cache object for invalidation on UI events.

        The cache must implement an invalidate(hwnd: int) method.
        """
        self._cache = cache

    def _event_loop(self) -> None:
        """Main event loop running on the daemon thread.

        Initializes COM, installs WinEventHooks, and runs a PeekMessage pump.
        """
        try:
            # Initialize COM for this thread
            ole32 = ctypes.windll.ole32
            hr = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
            if hr < 0 and hr != -2147417850:  # RPC_E_CHANGED_MODE is ok
                logger.warning("CoInitializeEx returned 0x%08X", hr & 0xFFFFFFFF)

            try:
                # Create the callback
                self._callback_ref = WINEVENTPROC(self._win_event_callback)

                # Install hooks for each event type
                events_to_hook = [
                    EVENT_OBJECT_FOCUS,
                    EVENT_OBJECT_STATECHANGE,
                    EVENT_OBJECT_NAMECHANGE,
                    EVENT_OBJECT_CREATE,
                    EVENT_OBJECT_DESTROY,
                    EVENT_SYSTEM_FOREGROUND,
                ]

                user32 = ctypes.windll.user32

                for event_id in events_to_hook:
                    hook = user32.SetWinEventHook(
                        event_id,         # eventMin
                        event_id,         # eventMax
                        None,             # hmodWinEventProc (None = out-of-context)
                        self._callback_ref,
                        0,                # idProcess (0 = all processes)
                        0,                # idThread (0 = all threads)
                        WINEVENT_OUTOFCONTEXT,
                    )
                    if hook:
                        self._hooks.append(hook)
                    else:
                        logger.debug("Failed to set WinEventHook for event 0x%04X", event_id)

                # Message pump loop
                msg = ctypes.wintypes.MSG()
                while not self._stop_event.is_set():
                    # PeekMessage with timeout via short sleep
                    result = user32.PeekMessageW(
                        ctypes.byref(msg), None, 0, 0, PM_REMOVE
                    )
                    if result:
                        if msg.message == WM_QUIT:
                            break
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    else:
                        # No message available — short sleep to avoid busy-wait
                        self._stop_event.wait(timeout=0.01)

            finally:
                # Unhook all event hooks
                user32 = ctypes.windll.user32
                for hook in self._hooks:
                    try:
                        user32.UnhookWinEvent(hook)
                    except Exception:
                        pass
                self._hooks.clear()

                ole32.CoUninitialize()

        except Exception as exc:
            logger.error("EventManager event loop crashed: %s", exc, exc_info=True)

    def _win_event_callback(
        self,
        hook: int,
        event: int,
        hwnd: int,
        id_object: int,
        id_child: int,
        event_thread: int,
        event_time: int,
    ) -> None:
        """Callback invoked by Windows when a UI event occurs."""
        try:
            # Filter to registered windows only (if any are registered)
            with self._lock:
                if self._registered_hwnds and hwnd not in self._registered_hwnds:
                    return

            event_name = _EVENT_NAMES.get(event, f"unknown_0x{event:04X}")

            # Try to get window title for element_name
            element_name = None
            try:
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                element_name = buf.value or None
            except Exception:
                pass

            event_info = EventInfo(
                event_type=event_name,
                hwnd=hwnd,
                element_name=element_name,
                timestamp=time.time(),
            )

            with self._lock:
                self._events.append(event_info)

            # Invalidate cache if wired
            if self._cache is not None:
                try:
                    self._cache.invalidate(hwnd)
                except Exception:
                    pass

        except Exception:
            # Never let callback exceptions propagate to Windows
            pass


# Module-level singleton
_event_manager: EventManager | None = None
_manager_lock = threading.Lock()


def get_event_manager() -> EventManager:
    """Get the singleton EventManager instance."""
    global _event_manager
    if _event_manager is None:
        with _manager_lock:
            if _event_manager is None:
                _event_manager = EventManager()
    return _event_manager
