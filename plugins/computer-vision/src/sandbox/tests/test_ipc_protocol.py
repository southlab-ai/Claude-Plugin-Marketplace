"""Tests for the IPC wire protocol (src/sandbox/ipc/protocol.py)."""

from __future__ import annotations

import json
import struct

import pytest

from src.sandbox.ipc.protocol import (
    ALL_METHODS,
    AUTH_TIMEOUT_S,
    CAPTURE_FRAME,
    DEFAULT_TIMEOUT_S,
    GET_SCENE_GRAPH,
    HEADER_FORMAT,
    HEADER_SIZE,
    HEARTBEAT_INTERVAL_S,
    INJECT_CLICK,
    INJECT_KEYS,
    INJECT_MESSAGE,
    MAX_FRAME_SIZE,
    MSG_AUTH,
    MSG_AUTH_FAIL,
    MSG_AUTH_OK,
    MSG_HEARTBEAT,
    PING,
    AuthenticationError,
    FrameTooLargeError,
    ProtocolError,
    decode_frame_body,
    decode_frame_header,
    encode_frame,
    make_auth,
    make_heartbeat,
    make_request,
    make_response,
)


class TestEncodeFrame:
    """Tests for encode_frame."""

    def test_encode_frame_basic(self) -> None:
        """Encode a simple dict; verify 4-byte header + JSON body."""
        data = {"hello": "world", "num": 42}
        raw = encode_frame(data)

        # First 4 bytes are the header
        assert len(raw) >= HEADER_SIZE
        header_bytes = raw[:HEADER_SIZE]
        body_bytes = raw[HEADER_SIZE:]

        # Header should be LE uint32 of body length
        (length,) = struct.unpack(HEADER_FORMAT, header_bytes)
        assert length == len(body_bytes)

        # Body should be valid JSON matching the original dict
        decoded = json.loads(body_bytes.decode("utf-8"))
        assert decoded == data

    def test_encode_frame_empty(self) -> None:
        """Encode an empty dict."""
        raw = encode_frame({})
        header_bytes = raw[:HEADER_SIZE]
        body_bytes = raw[HEADER_SIZE:]

        (length,) = struct.unpack(HEADER_FORMAT, header_bytes)
        assert length == len(body_bytes)
        assert json.loads(body_bytes.decode("utf-8")) == {}

    def test_encode_frame_too_large(self) -> None:
        """Encoding a dict that exceeds 16MB raises FrameTooLargeError."""
        # Build a dict whose JSON representation exceeds MAX_FRAME_SIZE
        huge_value = "x" * (MAX_FRAME_SIZE + 1)
        with pytest.raises(FrameTooLargeError):
            encode_frame({"data": huge_value})


class TestDecodeFrameHeader:
    """Tests for decode_frame_header."""

    def test_decode_frame_header_valid(self) -> None:
        """Decode a valid 4-byte header."""
        expected_length = 256
        header_bytes = struct.pack(HEADER_FORMAT, expected_length)
        assert decode_frame_header(header_bytes) == expected_length

    def test_decode_frame_header_wrong_size(self) -> None:
        """Decode with wrong number of bytes raises ProtocolError."""
        with pytest.raises(ProtocolError):
            decode_frame_header(b"\x00\x00")  # only 2 bytes

        with pytest.raises(ProtocolError):
            decode_frame_header(b"\x00\x00\x00\x00\x00")  # 5 bytes

        with pytest.raises(ProtocolError):
            decode_frame_header(b"")  # 0 bytes

    def test_decode_frame_header_too_large(self) -> None:
        """Header indicating >16MB raises FrameTooLargeError."""
        over_limit = MAX_FRAME_SIZE + 1
        header_bytes = struct.pack(HEADER_FORMAT, over_limit)
        with pytest.raises(FrameTooLargeError):
            decode_frame_header(header_bytes)

    def test_decode_frame_header_boundary(self) -> None:
        """Header at exactly MAX_FRAME_SIZE should succeed."""
        header_bytes = struct.pack(HEADER_FORMAT, MAX_FRAME_SIZE)
        assert decode_frame_header(header_bytes) == MAX_FRAME_SIZE


class TestDecodeFrameBody:
    """Tests for decode_frame_body."""

    def test_decode_frame_body_valid(self) -> None:
        """Decode valid UTF-8 JSON body."""
        data = {"key": "value", "num": 123}
        body_bytes = json.dumps(data).encode("utf-8")
        assert decode_frame_body(body_bytes) == data

    def test_decode_frame_body_invalid_json(self) -> None:
        """Decode bad JSON raises ProtocolError."""
        with pytest.raises(ProtocolError):
            decode_frame_body(b"not-json{{{")

    def test_decode_frame_body_not_dict(self) -> None:
        """Decode JSON array raises ProtocolError."""
        with pytest.raises(ProtocolError):
            decode_frame_body(b'[1, 2, 3]')

        # Also test with a string
        with pytest.raises(ProtocolError):
            decode_frame_body(b'"just a string"')

        # Also test with a number
        with pytest.raises(ProtocolError):
            decode_frame_body(b'42')


class TestRoundTrip:
    """End-to-end encode/decode tests."""

    def test_round_trip(self) -> None:
        """Encode then decode; verify data matches."""
        original = {"id": 1, "method": "ping", "params": {"foo": "bar"}}
        raw = encode_frame(original)

        # Decode header
        header_bytes = raw[:HEADER_SIZE]
        body_length = decode_frame_header(header_bytes)

        # Decode body
        body_bytes = raw[HEADER_SIZE : HEADER_SIZE + body_length]
        result = decode_frame_body(body_bytes)

        assert result == original

    def test_round_trip_nested(self) -> None:
        """Round-trip with nested structures."""
        original = {
            "id": 99,
            "result": {
                "windows": [
                    {"hwnd": 100, "title": "Notepad"},
                    {"hwnd": 200, "title": "Explorer"},
                ],
                "count": 2,
            },
            "error": None,
        }
        raw = encode_frame(original)
        header_bytes = raw[:HEADER_SIZE]
        body_length = decode_frame_header(header_bytes)
        body_bytes = raw[HEADER_SIZE : HEADER_SIZE + body_length]
        result = decode_frame_body(body_bytes)
        assert result == original


class TestMakeRequest:
    """Tests for make_request."""

    def test_make_request(self) -> None:
        """Verify request envelope structure."""
        req = make_request(1, "ping")
        assert req["id"] == 1
        assert req["method"] == "ping"
        assert "params" not in req  # no params when None

    def test_make_request_with_params(self) -> None:
        """Request with params includes them."""
        params = {"x": 100, "y": 200}
        req = make_request(42, "inject_click", params)
        assert req["id"] == 42
        assert req["method"] == "inject_click"
        assert req["params"] == params

    def test_make_request_empty_params_excluded(self) -> None:
        """Empty params dict is falsy, so excluded from message."""
        req = make_request(1, "ping", {})
        assert "params" not in req


class TestMakeResponse:
    """Tests for make_response."""

    def test_make_response(self) -> None:
        """Verify response envelope structure."""
        resp = make_response(1, result={"status": "ok"})
        assert resp["id"] == 1
        assert resp["result"] == {"status": "ok"}
        assert resp["error"] is None

    def test_make_response_error(self) -> None:
        """Response with error string."""
        resp = make_response(2, error="something broke")
        assert resp["id"] == 2
        assert resp["result"] == {}  # default empty dict
        assert resp["error"] == "something broke"

    def test_make_response_defaults(self) -> None:
        """Response with no result or error uses defaults."""
        resp = make_response(3)
        assert resp["id"] == 3
        assert resp["result"] == {}
        assert resp["error"] is None


class TestMakeAuth:
    """Tests for make_auth."""

    def test_make_auth(self) -> None:
        """Verify auth frame structure."""
        token = "abcdef0123456789"
        auth = make_auth(token)
        assert auth["type"] == MSG_AUTH
        assert auth["token"] == token

    def test_make_auth_keys(self) -> None:
        """Auth frame has exactly two keys."""
        auth = make_auth("test")
        assert set(auth.keys()) == {"type", "token"}


class TestMakeHeartbeat:
    """Tests for make_heartbeat."""

    def test_make_heartbeat(self) -> None:
        """Verify heartbeat structure."""
        hb = make_heartbeat(timestamp_ms=1000, version=5)
        assert hb["type"] == MSG_HEARTBEAT
        assert hb["ts"] == 1000
        assert hb["version"] == 5

    def test_make_heartbeat_keys(self) -> None:
        """Heartbeat has exactly three keys."""
        hb = make_heartbeat(0, 0)
        assert set(hb.keys()) == {"type", "ts", "version"}


class TestAllMethods:
    """Tests for ALL_METHODS constant."""

    def test_all_methods_defined(self) -> None:
        """ALL_METHODS contains all expected method names."""
        expected = {
            GET_SCENE_GRAPH,
            INJECT_CLICK,
            INJECT_KEYS,
            INJECT_MESSAGE,
            CAPTURE_FRAME,
            PING,
        }
        assert ALL_METHODS == expected

    def test_all_methods_strings(self) -> None:
        """ALL_METHODS values are all strings."""
        for method in ALL_METHODS:
            assert isinstance(method, str)

    def test_all_methods_immutable(self) -> None:
        """ALL_METHODS is a frozenset (immutable)."""
        assert isinstance(ALL_METHODS, frozenset)


class TestConstants:
    """Sanity-check protocol constants."""

    def test_max_frame_size(self) -> None:
        assert MAX_FRAME_SIZE == 16 * 1024 * 1024

    def test_header_size(self) -> None:
        assert HEADER_SIZE == 4

    def test_heartbeat_interval(self) -> None:
        assert HEARTBEAT_INTERVAL_S == 5.0

    def test_auth_timeout(self) -> None:
        assert AUTH_TIMEOUT_S == 10.0

    def test_default_timeout(self) -> None:
        assert DEFAULT_TIMEOUT_S == 5.0
