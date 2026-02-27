"""TCP IPC client for communicating with the sandbox shim DLL."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Any

from src.sandbox.ipc.protocol import (
    AUTH_TIMEOUT_S,
    DEFAULT_TIMEOUT_S,
    HEADER_SIZE,
    MAX_FRAME_SIZE,
    MSG_AUTH,
    MSG_AUTH_FAIL,
    MSG_AUTH_OK,
    MSG_HEARTBEAT,
    AuthenticationError,
    FrameTooLargeError,
    ProtocolError,
    decode_frame_body,
    decode_frame_header,
    encode_frame,
    make_auth,
    make_request,
)

logger = logging.getLogger(__name__)

# Reconnection backoff schedule (seconds)
_RECONNECT_DELAYS = (0.5, 1.0, 2.0)
_MAX_RECONNECT_ATTEMPTS = len(_RECONNECT_DELAYS)

# Port discovery
_PORT_POLL_INTERVAL = 0.5  # seconds between retries
_PORT_DISCOVERY_TIMEOUT = 30.0  # max wait for shim_port.txt


class ShimIPCClient:
    """Thread-safe TCP client for the sandbox shim IPC protocol.

    Handles port discovery, authentication, heartbeat filtering,
    and automatic reconnection with exponential backoff.
    """

    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._connected = False
        self._host: str = ""
        self._port: int = 0
        self._token: str = ""

    # ------------------------------------------------------------------
    # Port discovery
    # ------------------------------------------------------------------

    @staticmethod
    def discover_port(comm_folder: str | Path, timeout: float = _PORT_DISCOVERY_TIMEOUT) -> int:
        """Read shim_port.txt from the mapped communication folder.

        Polls with backoff until the file appears or *timeout* seconds elapse.

        Returns:
            The port number read from the file.

        Raises:
            TimeoutError: If the port file does not appear within *timeout*.
            ValueError: If the file content is not a valid port number.
        """
        port_file = Path(comm_folder) / "shim_port.txt"
        deadline = time.monotonic() + timeout
        delay = _PORT_POLL_INTERVAL

        while time.monotonic() < deadline:
            if port_file.exists():
                raw = port_file.read_text(encoding="utf-8").strip()
                if raw:
                    port = int(raw)
                    if not (1 <= port <= 65535):
                        raise ValueError(f"Port out of range: {port}")
                    logger.info("Discovered shim port %d from %s", port, port_file)
                    return port
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(delay, remaining))
            delay = min(delay * 1.5, 3.0)  # gentle backoff

        raise TimeoutError(
            f"shim_port.txt not found in {comm_folder} within {timeout}s"
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, host: str, port: int, token: str, timeout: float = AUTH_TIMEOUT_S) -> None:
        """Establish TCP connection and perform auth handshake.

        Args:
            host: Server hostname / IP (typically '127.0.0.1').
            port: Server port.
            token: Hex-encoded auth token.
            timeout: Socket timeout for the auth phase.

        Raises:
            ConnectionError: If TCP connection fails.
            AuthenticationError: If the server rejects the token.
            ProtocolError: If the server response is malformed.
        """
        with self._lock:
            self._close_socket()
            self._host = host
            self._port = port
            self._token = token
            self._do_connect(timeout)

    def _do_connect(self, timeout: float = AUTH_TIMEOUT_S) -> None:
        """Internal connect + auth (caller must hold _lock)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self._host, self._port))
        except OSError as exc:
            sock.close()
            raise ConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {exc}"
            ) from exc

        self._sock = sock
        self._connected = False

        # --- Auth handshake ---
        auth_msg = make_auth(self._token)
        self._send_frame_raw(auth_msg)

        # Read auth response (skip heartbeats)
        response = self._recv_frame_raw(timeout=timeout)
        msg_type = response.get("type", "")
        if msg_type == MSG_AUTH_OK:
            self._connected = True
            self._sock.settimeout(DEFAULT_TIMEOUT_S)
            logger.info("Authenticated with shim at %s:%d", self._host, self._port)
        elif msg_type == MSG_AUTH_FAIL:
            reason = response.get("reason", "unknown")
            self._close_socket()
            raise AuthenticationError(f"Auth rejected: {reason}")
        else:
            self._close_socket()
            raise ProtocolError(f"Unexpected auth response type: {msg_type!r}")

    # ------------------------------------------------------------------
    # Send / Receive
    # ------------------------------------------------------------------

    def send_request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = DEFAULT_TIMEOUT_S
    ) -> dict[str, Any]:
        """Send a request and return the matching response result.

        Heartbeat frames are silently consumed while waiting.

        Args:
            method: IPC method name (e.g. 'get_scene_graph').
            params: Optional parameters dict.
            timeout: Receive timeout in seconds.

        Returns:
            The 'result' dict from the response.

        Raises:
            ConnectionError: If not connected or connection lost.
            ProtocolError: On wire-level errors.
            RuntimeError: If the server returns an error field.
        """
        with self._lock:
            if not self._connected or self._sock is None:
                raise ConnectionError("Not connected to shim")

            self._request_id += 1
            req_id = self._request_id
            req = make_request(req_id, method, params)

            # Try with reconnect
            for attempt in range(_MAX_RECONNECT_ATTEMPTS + 1):
                try:
                    self._send_frame_raw(req)
                    response = self._recv_response(req_id, timeout)
                    error = response.get("error")
                    if error:
                        raise RuntimeError(f"Shim error for {method}: {error}")
                    return response.get("result", {})
                except (OSError, ConnectionError, ProtocolError) as exc:
                    if attempt < _MAX_RECONNECT_ATTEMPTS:
                        delay = _RECONNECT_DELAYS[attempt]
                        logger.warning(
                            "IPC request failed (attempt %d/%d): %s — reconnecting in %.1fs",
                            attempt + 1,
                            _MAX_RECONNECT_ATTEMPTS + 1,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                        try:
                            self._do_connect()
                            # Re-send with same request id
                            self._send_frame_raw(req)
                            response = self._recv_response(req_id, timeout)
                            error = response.get("error")
                            if error:
                                raise RuntimeError(f"Shim error for {method}: {error}")
                            return response.get("result", {})
                        except Exception:
                            continue
                    else:
                        raise ConnectionError(
                            f"IPC request failed after {_MAX_RECONNECT_ATTEMPTS + 1} attempts"
                        ) from exc

            raise ConnectionError("IPC request failed — exhausted all retries")

    def _recv_response(self, expected_id: int, timeout: float) -> dict[str, Any]:
        """Receive frames until we get a response matching *expected_id*.

        Heartbeat frames are silently skipped.
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError(f"Timeout waiting for response id={expected_id}")
            frame = self._recv_frame_raw(timeout=remaining)
            # Skip heartbeats
            if frame.get("type") == MSG_HEARTBEAT:
                continue
            # Check for matching response (has "id" field)
            if "id" in frame:
                if frame["id"] == expected_id:
                    return frame
                logger.debug(
                    "Discarding stale response id=%s (expected %s)", frame["id"], expected_id
                )
                continue
            # Skip any other non-response frames
            logger.debug("Skipping non-response frame: %s", frame.get("type", "unknown"))

    # ------------------------------------------------------------------
    # Raw frame I/O (caller must hold _lock)
    # ------------------------------------------------------------------

    def _send_frame_raw(self, data: dict[str, Any]) -> None:
        """Encode and send a single frame (no lock)."""
        if self._sock is None:
            raise ConnectionError("Socket not connected")
        raw = encode_frame(data)
        self._sock.sendall(raw)

    def _recv_frame_raw(self, timeout: float | None = None) -> dict[str, Any]:
        """Receive and decode a single frame (no lock)."""
        if self._sock is None:
            raise ConnectionError("Socket not connected")
        if timeout is not None:
            self._sock.settimeout(timeout)
        # Read header
        header = self._recv_exact(HEADER_SIZE)
        body_len = decode_frame_header(header)
        if body_len == 0:
            raise ProtocolError("Received zero-length frame")
        body_bytes = self._recv_exact(body_len)
        return decode_frame_body(body_bytes)

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly *n* bytes from the socket."""
        if self._sock is None:
            raise ConnectionError("Socket not connected")
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by remote")
            buf.extend(chunk)
        return bytes(buf)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """True if the client believes it is connected and authenticated."""
        return self._connected and self._sock is not None

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self._close_socket()

    def _close_socket(self) -> None:
        """Internal close (caller must hold _lock)."""
        self._connected = False
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
