"""Chrome DevTools Protocol adapter for Chromium-based browsers.

Uses WebSocket-based CDP via ``websocket-client`` to interact with Chrome,
Edge, Brave, Vivaldi, and Opera.  Replaces the previous non-functional
HTTP-POST implementation.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import logging
import re
import threading
import time
from typing import Any, NamedTuple
from urllib.parse import urlparse

import httpx
import websocket  # websocket-client

from src.adapters import AdapterRegistry, BaseAdapter
from src.config import CDP_MAX_CONNECTIONS, CDP_PORT
from src.models import ActionResult, FallbackStep, VerificationResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_HOST = "127.0.0.1"
_PROBE_TIMEOUT = 0.5  # 500 ms
_TAB_CACHE_TTL = 30.0  # seconds
_CSS_SELECTOR_MAX_LEN = 256
_CSS_SELECTOR_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_\.#\[\]=:>\"'*,()^~\|+]+$")
_CSS_SELECTOR_BLOCKLIST = re.compile(
    r"javascript:|expression\(|url\(|@import|<script|`", re.IGNORECASE
)
_WS_GUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_BROWSER_SUFFIXES = (
    " - Google Chrome",
    " - Microsoft Edge",
    " - Brave",
    " - Vivaldi",
    " - Opera",
)

# Predefined safe queries for Runtime.evaluate
_SAFE_QUERIES: dict[str, str] = {
    "get_title": "document.title",
    "get_url": "window.location.href",
    "get_body_text": "document.body.innerText",
    "get_ready_state": "document.readyState",
}

# ---------------------------------------------------------------------------
# A1: Security helpers
# ---------------------------------------------------------------------------


def _sanitize_css_selector(selector: str) -> str:
    """Validate and return a CSS selector, or raise ``ValueError``."""
    if not selector or len(selector) > _CSS_SELECTOR_MAX_LEN:
        raise ValueError(f"CSS selector invalid length ({len(selector)})")
    if _CSS_SELECTOR_BLOCKLIST.search(selector):
        raise ValueError("CSS selector contains blocked pattern")
    if not _CSS_SELECTOR_PATTERN.match(selector):
        raise ValueError("CSS selector contains disallowed characters")
    return selector


def _validate_ws_url(url: str, expected_port: int) -> str:
    """Ensure *url* is a ``ws://127.0.0.1:<port>/...`` URL."""
    parsed = urlparse(url)
    if parsed.scheme != "ws":
        raise ValueError(f"Expected ws:// scheme, got {parsed.scheme}")
    if parsed.hostname != _ALLOWED_HOST:
        raise ValueError(f"Expected host {_ALLOWED_HOST}, got {parsed.hostname}")
    if parsed.port != expected_port:
        raise ValueError(f"Expected port {expected_port}, got {parsed.port}")
    return url


def _redact_ws_url(url: str) -> str:
    """Replace GUID in a WebSocket URL with ``[REDACTED]``."""
    return _WS_GUID_PATTERN.sub("[REDACTED]", url)


def _validate_cdp_response(response: dict, command_id: int) -> dict:
    """Validate a CDP JSON-RPC response and return its ``result`` dict."""
    if response.get("id") != command_id:
        raise RuntimeError(
            f"CDP response id mismatch: expected {command_id}, got {response.get('id')}"
        )
    if "error" in response:
        err = response["error"]
        msg = err.get("message", str(err))
        raise RuntimeError(f"CDP error: {msg}")
    return response.get("result", {})


# ---------------------------------------------------------------------------
# A2: _CDPConnection
# ---------------------------------------------------------------------------


class _CDPConnection:
    """A single WebSocket connection to a CDP target."""

    def __init__(self, ws_url: str, timeout: float = 5.0) -> None:
        _validate_ws_url(ws_url, CDP_PORT)
        self._ws_url = ws_url
        self._timeout = timeout
        self._msg_id = 0
        self._lock = threading.Lock()
        self._ws: websocket.WebSocket = websocket.create_connection(
            ws_url, timeout=timeout
        )

    def send(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command and return the validated result dict."""
        with self._lock:
            self._msg_id += 1
            mid = self._msg_id
            payload = {"id": mid, "method": method}
            if params:
                payload["params"] = params
            self._ws.send(json.dumps(payload))
            # Read responses, discarding push events until we get our reply
            while True:
                raw = self._ws.recv()
                msg = json.loads(raw)
                if "id" in msg and msg["id"] == mid:
                    return _validate_cdp_response(msg, mid)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    @property
    def connected(self) -> bool:
        try:
            return self._ws.connected
        except Exception:
            return False


# ---------------------------------------------------------------------------
# A3: _CDPConnectionPool
# ---------------------------------------------------------------------------


class _CDPConnectionPool:
    """Thread-safe pool of CDP connections keyed by WebSocket URL."""

    def __init__(self) -> None:
        self._pool: dict[str, _CDPConnection] = {}
        self._order: list[str] = []  # LRU tracking (most recent at end)
        self._lock = threading.Lock()
        atexit.register(self.close_all)

    def acquire(self, ws_url: str) -> _CDPConnection:
        with self._lock:
            conn = self._pool.get(ws_url)
            if conn is not None and conn.connected:
                # Bump LRU
                if ws_url in self._order:
                    self._order.remove(ws_url)
                self._order.append(ws_url)
                return conn
            # Evict stale entry if present
            if conn is not None:
                conn.close()
                del self._pool[ws_url]
                if ws_url in self._order:
                    self._order.remove(ws_url)
            # Evict LRU if at capacity
            while len(self._pool) >= CDP_MAX_CONNECTIONS and self._order:
                oldest = self._order.pop(0)
                old_conn = self._pool.pop(oldest, None)
                if old_conn is not None:
                    old_conn.close()
            # Create new connection
            conn = _CDPConnection(ws_url)
            self._pool[ws_url] = conn
            self._order.append(ws_url)
            return conn

    def evict(self, ws_url: str) -> None:
        with self._lock:
            conn = self._pool.pop(ws_url, None)
            if conn is not None:
                conn.close()
            if ws_url in self._order:
                self._order.remove(ws_url)

    def close_all(self) -> None:
        with self._lock:
            for conn in self._pool.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()
            self._order.clear()


# ---------------------------------------------------------------------------
# A4: _CDPTabResolver
# ---------------------------------------------------------------------------


class _CachedTab(NamedTuple):
    ws_url: str
    target_id: str
    expires: float


class _CDPTabResolver:
    """Resolves a Win32 HWND to a CDP WebSocket debugger URL."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._cache: dict[int, _CachedTab] = {}

    def resolve(self, hwnd: int) -> str | None:
        """Return the ``webSocketDebuggerUrl`` for the tab matching *hwnd*."""
        # Check cache
        cached = self._cache.get(hwnd)
        if cached is not None and cached.expires > time.monotonic():
            return cached.ws_url

        # Get window title via Win32
        title = self._get_window_title(hwnd)
        stripped_title = self._strip_browser_suffix(title)

        # Fetch target list
        try:
            resp = httpx.get(
                f"http://{_ALLOWED_HOST}:{self._port}/json",
                timeout=_PROBE_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            targets = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException, OSError, json.JSONDecodeError):
            return None

        # Match by title (substring)
        best: dict | None = None
        fallback: dict | None = None
        for t in targets:
            if t.get("type") != "page":
                continue
            if fallback is None:
                fallback = t
            target_title = t.get("title", "")
            if stripped_title and stripped_title in target_title:
                best = t
                break

        chosen = best or fallback
        if chosen is None:
            return None

        ws_url = chosen.get("webSocketDebuggerUrl")
        if ws_url is None:
            return None

        try:
            _validate_ws_url(ws_url, self._port)
        except ValueError as exc:
            logger.warning("Invalid ws_url from /json: %s", exc)
            return None

        # Cache result
        self._cache[hwnd] = _CachedTab(
            ws_url=ws_url,
            target_id=chosen.get("id", ""),
            expires=time.monotonic() + _TAB_CACHE_TTL,
        )
        return ws_url

    def invalidate(self, hwnd: int) -> None:
        self._cache.pop(hwnd, None)

    @staticmethod
    def _get_window_title(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value

    @staticmethod
    def _strip_browser_suffix(title: str) -> str:
        for suffix in _BROWSER_SUFFIXES:
            if title.endswith(suffix):
                return title[: -len(suffix)].strip()
        return title


# ---------------------------------------------------------------------------
# A5: DOM operation functions
# ---------------------------------------------------------------------------


def _get_document_root(conn: _CDPConnection) -> int:
    result = conn.send("DOM.getDocument")
    return result["root"]["nodeId"]


def _query_selector(conn: _CDPConnection, root_id: int, selector: str) -> int:
    result = conn.send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
    node_id = result.get("nodeId", 0)
    if node_id == 0:
        raise ValueError(f"Element not found for selector: {selector}")
    return node_id


def _get_box_model(conn: _CDPConnection, node_id: int) -> dict:
    result = conn.send("DOM.getBoxModel", {"nodeId": node_id})
    content = result["model"]["content"]
    # content is 8 floats: x1,y1, x2,y2, x3,y3, x4,y4
    xs = [content[i] for i in (0, 2, 4, 6)]
    ys = [content[i] for i in (1, 3, 5, 7)]
    cx = sum(xs) / 4
    cy = sum(ys) / 4
    return {"x": cx, "y": cy, "content": content}


def _focus_node(conn: _CDPConnection, node_id: int) -> None:
    conn.send("DOM.focus", {"nodeId": node_id})


def _resolve_node(conn: _CDPConnection, node_id: int) -> str:
    result = conn.send("DOM.resolveNode", {"nodeId": node_id})
    return result["object"]["objectId"]


def _call_function_on(conn: _CDPConnection, object_id: str, fn_body: str) -> Any:
    result = conn.send(
        "Runtime.callFunctionOn",
        {"objectId": object_id, "functionDeclaration": fn_body, "returnByValue": True},
    )
    return result.get("result", {}).get("value")


def _get_outer_html(conn: _CDPConnection, node_id: int) -> str:
    result = conn.send("DOM.getOuterHTML", {"nodeId": node_id})
    return result.get("outerHTML", "")


def _dispatch_mouse_click(conn: _CDPConnection, x: float, y: float) -> None:
    conn.send(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    conn.send(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    )


def _dispatch_insert_text(conn: _CDPConnection, text: str) -> None:
    conn.send("Input.insertText", {"text": text})


def _clear_field(conn: _CDPConnection) -> None:
    # Ctrl+A
    conn.send(
        "Input.dispatchKeyEvent",
        {
            "type": "keyDown",
            "modifiers": 2,  # Ctrl
            "key": "a",
            "code": "KeyA",
            "windowsVirtualKeyCode": 65,
        },
    )
    conn.send(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "modifiers": 2,
            "key": "a",
            "code": "KeyA",
            "windowsVirtualKeyCode": 65,
        },
    )
    # Delete
    conn.send(
        "Input.dispatchKeyEvent",
        {
            "type": "keyDown",
            "key": "Delete",
            "code": "Delete",
            "windowsVirtualKeyCode": 46,
        },
    )
    conn.send(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "key": "Delete",
            "code": "Delete",
            "windowsVirtualKeyCode": 46,
        },
    )


# ---------------------------------------------------------------------------
# A6 / A7 / A8 / A9: ChromeCDPAdapter
# ---------------------------------------------------------------------------


class ChromeCDPAdapter(BaseAdapter):
    """Adapter that communicates with Chromium browsers via CDP over WebSocket."""

    _pool = _CDPConnectionPool()
    _resolver = _CDPTabResolver(CDP_PORT)

    # ---- BaseAdapter interface ----

    def probe(self, hwnd: int) -> bool:
        """Check if CDP is accessible on localhost."""
        try:
            resp = httpx.get(
                f"http://{_ALLOWED_HOST}:{CDP_PORT}/json/version",
                timeout=_PROBE_TIMEOUT,
            )
            return resp.status_code == 200
        except (httpx.HTTPError, httpx.TimeoutException, OSError):
            return False

    def supports_action(self, action: str) -> bool:
        return action in {"invoke", "set_value", "get_value", "get_text"}

    def execute(
        self, hwnd: int, target: str, action: str, value: str | None
    ) -> ActionResult:
        """Execute a CDP action against a browser tab matched by *hwnd*."""
        fallback_chain: list[FallbackStep] = []
        t0 = time.perf_counter()

        if not self.supports_action(action):
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                fallback_chain=fallback_chain,
            )

        try:
            selector = _sanitize_css_selector(target)
        except ValueError as exc:
            logger.warning("Invalid selector: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                fallback_chain=fallback_chain,
            )

        ws_url: str | None = None
        conn: _CDPConnection | None = None

        try:
            ws_url = self._resolver.resolve(hwnd)
            if ws_url is None:
                logger.warning("Could not resolve CDP tab for hwnd %d", hwnd)
                return ActionResult(
                    success=False, strategy_used="adapter_cdp", layer=0,
                    fallback_chain=fallback_chain,
                )

            conn = self._pool.acquire(ws_url)
            logger.debug("CDP acquired connection %s", _redact_ws_url(ws_url))

            # Dispatch action
            if action == "invoke":
                result = self._do_invoke(conn, selector)
            elif action == "set_value":
                result = self._do_set_value(conn, selector, value or "")
            elif action == "get_value":
                result = self._do_get_value(conn, selector)
            elif action == "get_text":
                result = self._do_get_text(conn, selector)
            else:
                result = ActionResult(success=False, strategy_used="adapter_cdp", layer=0)

            # Post-action verification
            verification = self._verify(conn, action, selector, value, result)
            result.verification = verification

            elapsed = (time.perf_counter() - t0) * 1000
            result.timing_ms = elapsed
            fallback_chain.append(
                FallbackStep(strategy="adapter_cdp", result="success", duration_ms=elapsed)
            )
            result.fallback_chain = fallback_chain
            return result

        except (ConnectionRefusedError, OSError) as exc:
            logger.warning("CDP connection error: %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            fallback_chain.append(
                FallbackStep(strategy="adapter_cdp", result="timeout", duration_ms=elapsed)
            )
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                timing_ms=elapsed, fallback_chain=fallback_chain,
            )

        except websocket.WebSocketTimeoutException as exc:
            logger.warning("CDP timeout: %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            fallback_chain.append(
                FallbackStep(strategy="adapter_cdp", result="timeout", duration_ms=elapsed)
            )
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                timing_ms=elapsed, fallback_chain=fallback_chain,
            )

        except websocket.WebSocketConnectionClosedException as exc:
            logger.warning("CDP connection closed: %s", exc)
            if ws_url:
                self._pool.evict(ws_url)
                self._resolver.invalidate(hwnd)
            elapsed = (time.perf_counter() - t0) * 1000
            fallback_chain.append(
                FallbackStep(strategy="adapter_cdp", result="timeout", duration_ms=elapsed)
            )
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                timing_ms=elapsed, fallback_chain=fallback_chain,
            )

        except ValueError as exc:
            # Element not found (nodeId == 0)
            logger.warning("CDP element error: %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            fallback_chain.append(
                FallbackStep(
                    strategy="adapter_cdp",
                    result="element_not_found",
                    duration_ms=elapsed,
                )
            )
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                timing_ms=elapsed, fallback_chain=fallback_chain,
            )

        except Exception as exc:
            logger.warning("CDP unexpected error: %s", exc)
            elapsed = (time.perf_counter() - t0) * 1000
            fallback_chain.append(
                FallbackStep(strategy="adapter_cdp", result="timeout", duration_ms=elapsed)
            )
            return ActionResult(
                success=False, strategy_used="adapter_cdp", layer=0,
                timing_ms=elapsed, fallback_chain=fallback_chain,
            )

    # ---- Public safe_evaluate ----

    def safe_evaluate(self, hwnd: int, query_name: str) -> str | None:
        """Run a predefined safe JavaScript query against the tab for *hwnd*.

        Only allows queries from the ``_SAFE_QUERIES`` whitelist.
        """
        expression = _SAFE_QUERIES.get(query_name)
        if expression is None:
            logger.warning("Blocked unsafe evaluate query: %s", query_name)
            return None

        try:
            ws_url = self._resolver.resolve(hwnd)
            if ws_url is None:
                return None
            conn = self._pool.acquire(ws_url)
            result = conn.send("Runtime.evaluate", {"expression": expression})
            return result.get("result", {}).get("value")
        except Exception as exc:
            logger.warning(
                "safe_evaluate(%s) failed: %s", query_name, exc
            )
            return None

    # ---- A7: Action handlers ----

    @staticmethod
    def _do_invoke(conn: _CDPConnection, selector: str) -> ActionResult:
        root = _get_document_root(conn)
        node_id = _query_selector(conn, root, selector)
        box = _get_box_model(conn, node_id)
        _dispatch_mouse_click(conn, box["x"], box["y"])
        return ActionResult(
            success=True,
            strategy_used="adapter_cdp",
            layer=0,
        )

    @staticmethod
    def _do_set_value(
        conn: _CDPConnection, selector: str, text: str
    ) -> ActionResult:
        root = _get_document_root(conn)
        node_id = _query_selector(conn, root, selector)
        _focus_node(conn, node_id)
        _clear_field(conn)
        _dispatch_insert_text(conn, text)
        return ActionResult(
            success=True,
            strategy_used="adapter_cdp",
            layer=0,
        )

    @staticmethod
    def _do_get_value(conn: _CDPConnection, selector: str) -> ActionResult:
        root = _get_document_root(conn)
        node_id = _query_selector(conn, root, selector)
        obj_id = _resolve_node(conn, node_id)
        val = _call_function_on(
            conn, obj_id, "function(){return this.value||this.textContent}"
        )
        return ActionResult(
            success=True,
            strategy_used="adapter_cdp",
            layer=0,
            element={"value": val},
        )

    @staticmethod
    def _do_get_text(conn: _CDPConnection, selector: str) -> ActionResult:
        root = _get_document_root(conn)
        node_id = _query_selector(conn, root, selector)
        obj_id = _resolve_node(conn, node_id)
        val = _call_function_on(conn, obj_id, "function(){return this.innerText}")
        return ActionResult(
            success=True,
            strategy_used="adapter_cdp",
            layer=0,
            element={"text": val},
        )

    # ---- A8: Post-action verification ----

    @staticmethod
    def _verify(
        conn: _CDPConnection,
        action: str,
        selector: str,
        value: str | None,
        result: ActionResult,
    ) -> VerificationResult:
        if not result.success:
            return VerificationResult(method="none", passed=False)

        try:
            if action == "set_value" and value is not None:
                # Re-read the field value
                root = _get_document_root(conn)
                node_id = _query_selector(conn, root, selector)
                obj_id = _resolve_node(conn, node_id)
                actual = _call_function_on(
                    conn,
                    obj_id,
                    "function(){return this.value||this.textContent}",
                )
                passed = (actual == value) if actual is not None else False
                return VerificationResult(
                    method="cdp_dom_readback",
                    passed=passed,
                    detail=f"expected={value!r}, actual={actual!r}" if not passed else "",
                )

            if action == "invoke":
                # Brief poll to check element state (500ms max, 50ms intervals)
                deadline = time.perf_counter() + 0.5
                passed = False
                while time.perf_counter() < deadline:
                    try:
                        root = _get_document_root(conn)
                        _query_selector(conn, root, selector)
                        passed = True
                        break
                    except (ValueError, RuntimeError):
                        time.sleep(0.05)
                return VerificationResult(
                    method="cdp_state_check", passed=passed
                )

            # get_value / get_text -- no meaningful verification
            return VerificationResult(method="none", passed=True)

        except Exception as exc:
            logger.debug("Verification failed: %s", exc)
            return VerificationResult(method="none", passed=False, detail=str(exc))


# ---------------------------------------------------------------------------
# A10: Self-registration
# ---------------------------------------------------------------------------

AdapterRegistry().register(
    ["chrome", "msedge", "brave", "vivaldi", "opera"], ChromeCDPAdapter
)
