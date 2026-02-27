"""Unit tests for ChromeCDPAdapter (WebSocket-based rewrite)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.adapters.chrome_cdp import (
    ChromeCDPAdapter,
    _CDPConnection,
    _CDPConnectionPool,
    _CDPTabResolver,
    _sanitize_css_selector,
    _validate_ws_url,
    _redact_ws_url,
    _validate_cdp_response,
    _SAFE_QUERIES,
    _ALLOWED_HOST,
    _CSS_SELECTOR_MAX_LEN,
)
from src.adapters import AdapterRegistry
from src.models import ActionResult, VerificationResult

# -- B1: Mock helpers -------------------------------------------------------

_WS_URL = "ws://127.0.0.1:9222/devtools/page/X"


def _mock_cdp_response(msg_id: int, result: dict) -> str:
    return json.dumps({"id": msg_id, "result": result})


def _mock_cdp_error(msg_id: int, code: int, message: str) -> str:
    return json.dumps({"id": msg_id, "error": {"code": code, "message": message}})


def _mock_cdp_event(method: str, params: dict) -> str:
    return json.dumps({"method": method, "params": params})


def _mock_tabs_json() -> list[dict]:
    return [
        {
            "id": "AAAA-1111",
            "type": "page",
            "title": "My Page",
            "url": "https://example.com",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/AAAA-1111",
        },
        {
            "id": "BBBB-2222",
            "type": "page",
            "title": "Other Page",
            "url": "https://other.com",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/BBBB-2222",
        },
    ]


def _mock_version_json() -> dict:
    return {
        "Browser": "Chrome/120.0.6099.130",
        "Protocol-Version": "1.3",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/GUID",
    }


# Mock send() return values — these are the UNWRAPPED result dicts
# (after _validate_cdp_response strips the JSON-RPC envelope)
_DOC = {"root": {"nodeId": 1}}
_QS = lambda nid: {"nodeId": nid}
_BOX = {"model": {"content": [100, 100, 200, 100, 200, 200, 100, 200]}}
_EMPTY = {}
_RESOLVE = {"object": {"objectId": "obj-1"}}
_FUNC = lambda v: {"result": {"value": v}}


def _make_adapter_with_mocks():
    adapter = ChromeCDPAdapter()
    mock_conn = MagicMock(spec=_CDPConnection)
    mock_resolver = MagicMock(spec=_CDPTabResolver)
    mock_pool = MagicMock(spec=_CDPConnectionPool)
    mock_resolver.resolve.return_value = _WS_URL
    mock_pool.acquire.return_value = mock_conn
    type(mock_conn).connected = PropertyMock(return_value=True)
    adapter._resolver = mock_resolver
    adapter._pool = mock_pool
    return adapter, mock_conn


# -- B2: Security functions --------------------------------------------------


class TestCssSanitization:
    def test_valid_simple_selector(self):
        assert _sanitize_css_selector("#submit-btn") == "#submit-btn"

    def test_valid_complex_selector(self):
        assert _sanitize_css_selector("input[name='email']") == "input[name='email']"

    def test_valid_combinators(self):
        assert _sanitize_css_selector("div > span.class") == "div > span.class"

    def test_reject_javascript_protocol(self):
        with pytest.raises(ValueError):
            _sanitize_css_selector("javascript:alert(1)")

    def test_reject_backtick(self):
        with pytest.raises(ValueError):
            _sanitize_css_selector("`onclick`")

    def test_reject_expression(self):
        with pytest.raises(ValueError):
            _sanitize_css_selector("expression(alert(1))")

    def test_reject_script_tag(self):
        with pytest.raises(ValueError):
            _sanitize_css_selector("<script>")

    def test_reject_too_long(self):
        with pytest.raises(ValueError):
            _sanitize_css_selector("a" * 257)

    def test_max_length_passes(self):
        assert _sanitize_css_selector("a" * 256) == "a" * 256


class TestWsUrlValidation:
    def test_valid_localhost_url(self):
        url = "ws://127.0.0.1:9222/devtools/page/ABC"
        assert _validate_ws_url(url, expected_port=9222) == url

    def test_reject_remote_host(self):
        with pytest.raises(ValueError):
            _validate_ws_url("ws://evil.com:9222/devtools/page/ABC", 9222)

    def test_reject_wrong_port(self):
        with pytest.raises(ValueError):
            _validate_ws_url("ws://127.0.0.1:9999/devtools/page/ABC", 9222)

    def test_reject_http_scheme(self):
        with pytest.raises(ValueError):
            _validate_ws_url("http://127.0.0.1:9222/devtools/page/ABC", 9222)


class TestUrlRedaction:
    def test_redacts_guid(self):
        url = "ws://127.0.0.1:9222/devtools/page/12345678-1234-1234-1234-123456789012"
        r = _redact_ws_url(url)
        assert "[REDACTED]" in r
        assert "12345678-1234-1234-1234-123456789012" not in r


class TestCdpResponseValidation:
    def test_valid_response_returns_result(self):
        resp = {"id": 1, "result": {"nodeId": 42}}
        assert _validate_cdp_response(resp, command_id=1) == {"nodeId": 42}

    def test_error_response_raises(self):
        with pytest.raises(RuntimeError):
            _validate_cdp_response(
                {"id": 1, "error": {"code": -1, "message": "fail"}}, 1
            )

    def test_id_mismatch_raises(self):
        with pytest.raises(RuntimeError):
            _validate_cdp_response({"id": 2, "result": {}}, command_id=1)


# -- B3: CDPConnection -------------------------------------------------------


class TestCDPConnection:
    @patch("websocket.create_connection")
    def test_send_constructs_json_rpc(self, mock_create):
        ws = MagicMock()
        ws.recv.return_value = _mock_cdp_response(1, {"nodeId": 1})
        mock_create.return_value = ws
        _CDPConnection(_WS_URL).send("DOM.getDocument")
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["method"] == "DOM.getDocument" and "id" in sent

    @patch("websocket.create_connection")
    def test_send_returns_validated_result(self, mock_create):
        ws = MagicMock()
        ws.recv.return_value = _mock_cdp_response(1, {"root": {"nodeId": 1}})
        mock_create.return_value = ws
        result = _CDPConnection(_WS_URL).send("DOM.getDocument")
        assert result == {"root": {"nodeId": 1}}

    @patch("websocket.create_connection")
    def test_send_skips_push_events(self, mock_create):
        ws = MagicMock()
        ws.recv.side_effect = [
            _mock_cdp_event("DOM.documentUpdated", {}),
            _mock_cdp_response(1, {"nodeId": 5}),
        ]
        mock_create.return_value = ws
        result = _CDPConnection(_WS_URL).send("DOM.getDocument")
        assert result["nodeId"] == 5

    @patch("websocket.create_connection")
    def test_send_timeout_raises(self, mock_create):
        import websocket

        ws = MagicMock()
        ws.recv.side_effect = websocket.WebSocketTimeoutException()
        mock_create.return_value = ws
        with pytest.raises(websocket.WebSocketTimeoutException):
            _CDPConnection(_WS_URL).send("DOM.getDocument")

    @patch("websocket.create_connection")
    def test_close_safe(self, mock_create):
        ws = MagicMock()
        ws.close.side_effect = Exception("already closed")
        mock_create.return_value = ws
        _CDPConnection(_WS_URL).close()  # must not raise

    @patch("websocket.create_connection")
    def test_connected_property(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        conn = _CDPConnection(_WS_URL)
        assert conn.connected is True
        type(ws).connected = PropertyMock(return_value=False)
        assert conn.connected is False

    def test_rejects_non_localhost_url(self):
        with pytest.raises(ValueError):
            _CDPConnection("ws://evil.com:9222/devtools/page/X")


# -- B4: CDPConnectionPool ---------------------------------------------------


class TestCDPConnectionPool:
    @patch("websocket.create_connection")
    def test_acquire_creates_new(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        assert _CDPConnectionPool().acquire(_WS_URL) is not None

    @patch("websocket.create_connection")
    def test_acquire_reuses_connected(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        pool = _CDPConnectionPool()
        c1 = pool.acquire(_WS_URL)
        c2 = pool.acquire(_WS_URL)
        assert c1 is c2 and mock_create.call_count == 1

    @patch("websocket.create_connection")
    def test_acquire_replaces_dead(self, mock_create):
        dead_ws = MagicMock()
        type(dead_ws).connected = PropertyMock(return_value=False)
        alive_ws = MagicMock()
        type(alive_ws).connected = PropertyMock(return_value=True)
        mock_create.side_effect = [dead_ws, alive_ws]
        pool = _CDPConnectionPool()
        c1 = pool.acquire(_WS_URL)
        c2 = pool.acquire(_WS_URL)
        assert c2 is not c1 and mock_create.call_count == 2

    @patch("websocket.create_connection")
    def test_max_connections_evicts_lru(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        pool = _CDPConnectionPool()
        for i in range(20):
            pool.acquire(f"ws://127.0.0.1:9222/devtools/page/{i}")
        assert mock_create.call_count == 20

    @patch("websocket.create_connection")
    def test_close_all(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        pool = _CDPConnectionPool()
        pool.acquire("ws://127.0.0.1:9222/devtools/page/A")
        pool.acquire("ws://127.0.0.1:9222/devtools/page/B")
        pool.close_all()  # smoke test — must not raise

    @patch("websocket.create_connection")
    def test_evict_removes(self, mock_create):
        ws = MagicMock()
        type(ws).connected = PropertyMock(return_value=True)
        mock_create.return_value = ws
        pool = _CDPConnectionPool()
        pool.acquire(_WS_URL)
        pool.evict(_WS_URL)
        pool.acquire(_WS_URL)
        assert mock_create.call_count == 2


# -- B5: CDPTabResolver ------------------------------------------------------


class TestCDPTabResolver:
    def _http_ok(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = _mock_tabs_json()
        return r

    @patch("httpx.get")
    @patch.object(
        _CDPTabResolver, "_get_window_title", return_value="My Page - Google Chrome"
    )
    def test_title_match_chrome(self, mock_txt, mock_http):
        mock_http.return_value = self._http_ok()
        ws = _CDPTabResolver(port=9222).resolve(hwnd=12345)
        assert ws and "AAAA-1111" in ws

    @patch("httpx.get")
    @patch.object(
        _CDPTabResolver, "_get_window_title", return_value="My Page - Microsoft Edge"
    )
    def test_title_match_edge(self, mock_txt, mock_http):
        mock_http.return_value = self._http_ok()
        ws = _CDPTabResolver(port=9222).resolve(hwnd=12345)
        assert ws and "AAAA-1111" in ws

    @patch("httpx.get")
    @patch.object(
        _CDPTabResolver, "_get_window_title", return_value="My Page - Google Chrome"
    )
    def test_cache_hit_within_ttl(self, mock_txt, mock_http):
        mock_http.return_value = self._http_ok()
        resolver = _CDPTabResolver(port=9222)
        resolver.resolve(12345)
        resolver.resolve(12345)
        assert mock_http.call_count == 1

    @patch("httpx.get")
    @patch.object(
        _CDPTabResolver, "_get_window_title", return_value="My Page - Google Chrome"
    )
    @patch("time.monotonic")
    def test_cache_miss_after_ttl(self, mock_time, mock_txt, mock_http):
        mock_http.return_value = self._http_ok()
        mock_time.side_effect = [0.0, 31.0, 31.0]
        resolver = _CDPTabResolver(port=9222)
        resolver.resolve(12345)
        resolver.resolve(12345)
        assert mock_http.call_count >= 2

    @patch("httpx.get")
    @patch.object(
        _CDPTabResolver,
        "_get_window_title",
        return_value="Unmatched - Google Chrome",
    )
    def test_no_match_fallback_first_page(self, mock_txt, mock_http):
        mock_http.return_value = self._http_ok()
        assert _CDPTabResolver(port=9222).resolve(12345) is not None

    @patch("httpx.get")
    def test_resolve_returns_none_on_error(self, mock_http):
        mock_http.side_effect = OSError("refused")
        assert _CDPTabResolver(port=9222).resolve(12345) is None


# -- B6: Probe ---------------------------------------------------------------


class TestProbe:
    def test_probe_success(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = _mock_version_json()
        with patch("httpx.get", return_value=r):
            assert ChromeCDPAdapter().probe(12345) is True

    def test_probe_connection_refused(self):
        with patch("httpx.get", side_effect=ConnectionError):
            assert ChromeCDPAdapter().probe(12345) is False

    def test_probe_timeout(self):
        import httpx

        with patch("httpx.get", side_effect=httpx.TimeoutException("t")):
            assert ChromeCDPAdapter().probe(12345) is False


# -- B7: Action handlers -----------------------------------------------------


class TestInvokeAction:
    def test_invoke_sends_correct_sequence(self):
        a, c = _make_adapter_with_mocks()
        # invoke: getDocument, querySelector, getBoxModel, mousePressed, mouseReleased
        # verify: getDocument, querySelector (one poll iteration)
        c.send.side_effect = [
            _DOC, _QS(42), _BOX, _EMPTY, _EMPTY,
            _DOC, _QS(42),
        ]
        r = a.execute(12345, "#submit-btn", "invoke", None)
        assert r.success is True
        methods = [call.args[0] for call in c.send.call_args_list]
        assert "DOM.getDocument" in methods and "DOM.querySelector" in methods

    def test_invoke_computes_center(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [
            _DOC, _QS(42), _BOX, _EMPTY, _EMPTY,
            _DOC, _QS(42),
        ]
        a.execute(12345, "#btn", "invoke", None)
        mouse_calls = [
            call
            for call in c.send.call_args_list
            if call.args[0] == "Input.dispatchMouseEvent"
        ]
        assert len(mouse_calls) == 2
        # Center of quad (100,100), (200,100), (200,200), (100,200) = (150, 150)
        assert mouse_calls[0].args[1]["x"] == 150.0
        assert mouse_calls[0].args[1]["y"] == 150.0


class TestSetValueAction:
    def _sides(self, readback_value):
        """Side effects for set_value + verification (12 sends total).

        Action: getDocument, querySelector, focus, 4x clear_field keys, insertText = 8
        Verify: getDocument, querySelector, resolveNode, callFunctionOn = 4
        """
        return [
            _DOC, _QS(42),
            _EMPTY,
            _EMPTY, _EMPTY, _EMPTY, _EMPTY,
            _EMPTY,
            _DOC, _QS(42), _RESOLVE, _FUNC(readback_value),
        ]

    def test_set_value_sends_correct_sequence(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = self._sides("hello")
        assert a.execute(12345, "#input", "set_value", "hello").success is True

    def test_set_value_verification_passes(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = self._sides("hello")
        r = a.execute(12345, "#input", "set_value", "hello")
        assert r.verification.passed is True
        assert r.verification.method == "cdp_dom_readback"

    def test_set_value_verification_fails(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = self._sides("wrong")
        r = a.execute(12345, "#input", "set_value", "hello")
        assert r.verification.passed is False


class TestGetValueAction:
    def test_get_value_returns_value(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [_DOC, _QS(42), _RESOLVE, _FUNC("hello")]
        r = a.execute(12345, "#input", "get_value", None)
        assert r.success and r.element and r.element.get("value") == "hello"


class TestGetTextAction:
    def test_get_text_returns_innertext(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [_DOC, _QS(42), _RESOLVE, _FUNC("visible text")]
        r = a.execute(12345, "div.content", "get_text", None)
        assert r.success and r.element and r.element.get("text") == "visible text"


# -- B8: Error handling -------------------------------------------------------


class TestErrorHandling:
    def test_connection_refused_probe_false(self):
        with patch("httpx.get", side_effect=ConnectionError):
            assert ChromeCDPAdapter().probe(12345) is False

    def test_resolver_failure_returns_failure(self):
        a, c = _make_adapter_with_mocks()
        a._resolver.resolve.return_value = None
        assert a.execute(12345, "#btn", "invoke", None).success is False

    def test_timeout_returns_failure(self):
        import websocket

        a, c = _make_adapter_with_mocks()
        c.send.side_effect = websocket.WebSocketTimeoutException()
        assert a.execute(12345, "#btn", "invoke", None).success is False

    def test_element_not_found(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [_DOC, _QS(0)]
        assert a.execute(12345, "#nope", "invoke", None).success is False

    def test_tab_closed_evicts_pool(self):
        import websocket

        a, c = _make_adapter_with_mocks()
        c.send.side_effect = websocket.WebSocketConnectionClosedException()
        a.execute(12345, "#btn", "invoke", None)
        a._pool.evict.assert_called()

    def test_invalid_selector_returns_failure(self):
        a, c = _make_adapter_with_mocks()
        assert a.execute(12345, "javascript:alert(1)", "invoke", None).success is False


# -- B9: Verification --------------------------------------------------------


class TestVerification:
    def test_set_value_readback_match(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [
            _DOC, _QS(42), _EMPTY,
            _EMPTY, _EMPTY, _EMPTY, _EMPTY,
            _EMPTY,
            _DOC, _QS(42), _RESOLVE, _FUNC("t"),
        ]
        v = a.execute(12345, "#i", "set_value", "t").verification
        assert v.method == "cdp_dom_readback" and v.passed is True

    def test_set_value_readback_mismatch(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [
            _DOC, _QS(42), _EMPTY,
            _EMPTY, _EMPTY, _EMPTY, _EMPTY,
            _EMPTY,
            _DOC, _QS(42), _RESOLVE, _FUNC("x"),
        ]
        assert a.execute(12345, "#i", "set_value", "t").verification.passed is False

    def test_invoke_state_check(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [
            _DOC, _QS(42), _BOX, _EMPTY, _EMPTY,
            _DOC, _QS(42),
        ]
        v = a.execute(12345, "#b", "invoke", None).verification
        assert v.method == "cdp_state_check"

    def test_get_value_no_verification(self):
        a, c = _make_adapter_with_mocks()
        c.send.side_effect = [_DOC, _QS(42), _RESOLVE, _FUNC("d")]
        v = a.execute(12345, "#i", "get_value", None).verification
        assert v.method == "none" and v.passed is True


# -- B10: Registration -------------------------------------------------------


class TestRegistration:
    def test_supports_invoke(self):
        assert ChromeCDPAdapter().supports_action("invoke")

    def test_supports_set_value(self):
        assert ChromeCDPAdapter().supports_action("set_value")

    def test_supports_get_value(self):
        assert ChromeCDPAdapter().supports_action("get_value")

    def test_supports_get_text(self):
        assert ChromeCDPAdapter().supports_action("get_text")

    def test_rejects_unknown_action(self):
        assert not ChromeCDPAdapter().supports_action("scroll")

    def test_registered_for_chrome(self):
        # Re-register since other test modules may reset the singleton
        AdapterRegistry().register(
            ["chrome", "msedge", "brave", "vivaldi", "opera"], ChromeCDPAdapter
        )
        assert "chrome" in AdapterRegistry()._pattern_map
