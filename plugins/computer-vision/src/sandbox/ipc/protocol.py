"""IPC wire protocol for sandbox shim TCP communication.

Framing: 4-byte little-endian uint32 length prefix + UTF-8 JSON body.
Auth: first frame from client is {"type": "auth", "token": "<hex>"}.
Heartbeat: server sends {"type": "heartbeat", "ts": <ms>, "version": <int>}.
Request: {"id": <int>, "method": "<name>", "params": {...}}.
Response: {"id": <int>, "result": {...}, "error": <str|null>}.
"""

from __future__ import annotations

import json
import struct
from typing import Any

# Protocol constants
MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MB
HEADER_SIZE = 4  # 4-byte LE uint32
HEADER_FORMAT = "<I"  # little-endian unsigned 32-bit
HEARTBEAT_INTERVAL_S = 5.0
AUTH_TIMEOUT_S = 10.0
DEFAULT_TIMEOUT_S = 5.0

# IPC method names
GET_SCENE_GRAPH = "get_scene_graph"
INJECT_CLICK = "inject_click"
INJECT_KEYS = "inject_keys"
INJECT_MESSAGE = "inject_message"
CAPTURE_FRAME = "capture_frame"
PING = "ping"

ALL_METHODS = frozenset(
    {GET_SCENE_GRAPH, INJECT_CLICK, INJECT_KEYS, INJECT_MESSAGE, CAPTURE_FRAME, PING}
)

# Message types (non-request/response)
MSG_AUTH = "auth"
MSG_AUTH_OK = "auth_ok"
MSG_AUTH_FAIL = "auth_fail"
MSG_HEARTBEAT = "heartbeat"


class FrameTooLargeError(Exception):
    """Raised when a frame exceeds MAX_FRAME_SIZE."""


class AuthenticationError(Exception):
    """Raised on authentication failure."""


class ProtocolError(Exception):
    """Raised on protocol-level errors (malformed frames, unexpected data)."""


def encode_frame(data: dict[str, Any]) -> bytes:
    """Encode a dict as a length-prefixed JSON frame.

    Returns bytes: 4-byte LE uint32 length + UTF-8 JSON body.
    Raises FrameTooLargeError if the encoded JSON exceeds MAX_FRAME_SIZE.
    """
    body = json.dumps(data, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME_SIZE:
        raise FrameTooLargeError(f"Frame size {len(body)} exceeds limit {MAX_FRAME_SIZE}")
    header = struct.pack(HEADER_FORMAT, len(body))
    return header + body


def decode_frame_header(header_bytes: bytes) -> int:
    """Decode a 4-byte frame header into the body length.

    Raises ProtocolError if header is invalid.
    Raises FrameTooLargeError if length exceeds MAX_FRAME_SIZE.
    """
    if len(header_bytes) != HEADER_SIZE:
        raise ProtocolError(f"Expected {HEADER_SIZE} header bytes, got {len(header_bytes)}")
    (length,) = struct.unpack(HEADER_FORMAT, header_bytes)
    if length > MAX_FRAME_SIZE:
        raise FrameTooLargeError(f"Frame size {length} exceeds limit {MAX_FRAME_SIZE}")
    return length


def decode_frame_body(body_bytes: bytes) -> dict[str, Any]:
    """Decode UTF-8 JSON body bytes into a dict.

    Raises ProtocolError if JSON is invalid.
    """
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"Invalid JSON frame: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError(f"Expected JSON object, got {type(data).__name__}")
    return data


def make_request(request_id: int, method: str, params: dict[str, Any] | None = None) -> dict:
    """Build a request envelope."""
    msg: dict[str, Any] = {"id": request_id, "method": method}
    if params:
        msg["params"] = params
    return msg


def make_response(
    request_id: int, result: dict[str, Any] | None = None, error: str | None = None
) -> dict:
    """Build a response envelope."""
    return {"id": request_id, "result": result or {}, "error": error}


def make_auth(token: str) -> dict:
    """Build an auth handshake frame."""
    return {"type": MSG_AUTH, "token": token}


def make_heartbeat(timestamp_ms: int, version: int) -> dict:
    """Build a heartbeat frame."""
    return {"type": MSG_HEARTBEAT, "ts": timestamp_ms, "version": version}
