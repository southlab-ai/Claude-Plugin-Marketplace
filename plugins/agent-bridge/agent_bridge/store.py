from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
TERMINAL_STATUSES = {"replied", "cancelled", "expired"}


class BridgeError(RuntimeError):
    """A user-correctable bridge protocol error."""


def default_db_path() -> Path:
    configured = os.environ.get("AGENT_BRIDGE_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".agent-bridge" / "bridge.sqlite3"


def validate_agent_name(name: str) -> str:
    if not AGENT_NAME_RE.fullmatch(name):
        raise BridgeError(
            "agent_name must be 1-64 characters using letters, digits, '_' or '-', "
            "and must start with a letter or digit"
        )
    return name


def validate_project_key(project_key: str) -> str:
    key = project_key.strip()
    if not key or len(key) > 256:
        raise BridgeError("project_key must contain 1-256 characters")
    return key


def validate_message(message: str) -> str:
    if not message.strip():
        raise BridgeError("message must not be empty")
    if len(message) > 200_000:
        raise BridgeError("message exceeds the 200000 character limit")
    return message


def validate_timeout(timeout_seconds: int) -> int:
    if not 1 <= timeout_seconds <= 7200:
        raise BridgeError("timeout_seconds must be between 1 and 7200")
    return timeout_seconds


@dataclass(frozen=True)
class RequestRecord:
    request_id: str
    project_key: str
    from_agent: str
    to_agent: str
    message: str
    status: str
    response: str | None
    created_at: float
    delivered_at: float | None
    replied_at: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "project_key": self.project_key,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message": self.message,
            "status": self.status,
            "response": self.response,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "replied_at": self.replied_at,
        }


class BridgeStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db_path.parent.chmod(0o700)
        except OSError:
            pass
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    project_key TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    registered_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    PRIMARY KEY (project_key, agent_name)
                );

                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'delivered', 'replied', 'cancelled', 'expired')
                    ),
                    response TEXT,
                    created_at REAL NOT NULL,
                    delivered_at REAL,
                    delivery_lease_until REAL,
                    replied_at REAL,
                    cancelled_at REAL,
                    FOREIGN KEY (project_key, from_agent)
                        REFERENCES agents(project_key, agent_name),
                    FOREIGN KEY (project_key, to_agent)
                        REFERENCES agents(project_key, agent_name)
                );

                CREATE INDEX IF NOT EXISTS idx_requests_recipient
                ON requests(project_key, to_agent, status, created_at);
                """
            )
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    def register_agent(
        self, project_key: str, agent_name: str, description: str = ""
    ) -> dict[str, Any]:
        project_key = validate_project_key(project_key)
        agent_name = validate_agent_name(agent_name)
        if len(description) > 1000:
            raise BridgeError("description exceeds the 1000 character limit")
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agents(project_key, agent_name, description, registered_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_key, agent_name) DO UPDATE SET
                    description = excluded.description,
                    last_seen_at = excluded.last_seen_at
                """,
                (project_key, agent_name, description, now, now),
            )
        return {
            "status": "registered",
            "project_key": project_key,
            "agent_name": agent_name,
            "description": description,
        }

    def _require_agent(
        self, connection: sqlite3.Connection, project_key: str, agent_name: str
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM agents WHERE project_key = ? AND agent_name = ?",
            (project_key, agent_name),
        ).fetchone()
        if row is None:
            raise BridgeError(
                f"agent '{agent_name}' is not registered in project '{project_key}'"
            )

    def create_request(
        self, project_key: str, from_agent: str, to_agent: str, message: str
    ) -> RequestRecord:
        project_key = validate_project_key(project_key)
        from_agent = validate_agent_name(from_agent)
        to_agent = validate_agent_name(to_agent)
        message = validate_message(message)
        if from_agent == to_agent:
            raise BridgeError("from_agent and to_agent must be different")
        request_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_agent(connection, project_key, from_agent)
            self._require_agent(connection, project_key, to_agent)
            connection.execute(
                """
                INSERT INTO requests(
                    request_id, project_key, from_agent, to_agent, message, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (request_id, project_key, from_agent, to_agent, message, now),
            )
            connection.execute(
                "UPDATE agents SET last_seen_at = ? WHERE project_key = ? AND agent_name = ?",
                (now, project_key, from_agent),
            )
            connection.commit()
        return self.get_request(request_id)

    def claim_request(
        self,
        project_key: str,
        agent_name: str,
        lease_seconds: int = 300,
    ) -> RequestRecord | None:
        project_key = validate_project_key(project_key)
        agent_name = validate_agent_name(agent_name)
        if not 30 <= lease_seconds <= 3600:
            raise BridgeError("lease_seconds must be between 30 and 3600")
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_agent(connection, project_key, agent_name)
            row = connection.execute(
                """
                SELECT * FROM requests
                WHERE project_key = ? AND to_agent = ?
                  AND (
                    status = 'pending'
                    OR (status = 'delivered' AND delivery_lease_until < ?)
                  )
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (project_key, agent_name, now),
            ).fetchone()
            if row is None:
                connection.execute(
                    "UPDATE agents SET last_seen_at = ? WHERE project_key = ? AND agent_name = ?",
                    (now, project_key, agent_name),
                )
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE requests
                SET status = 'delivered', delivered_at = ?, delivery_lease_until = ?
                WHERE request_id = ?
                """,
                (now, now + lease_seconds, row["request_id"]),
            )
            connection.execute(
                "UPDATE agents SET last_seen_at = ? WHERE project_key = ? AND agent_name = ?",
                (now, project_key, agent_name),
            )
            connection.commit()
        return self.get_request(row["request_id"])

    def reply(
        self, project_key: str, agent_name: str, request_id: str, message: str
    ) -> RequestRecord:
        project_key = validate_project_key(project_key)
        agent_name = validate_agent_name(agent_name)
        message = validate_message(message)
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_agent(connection, project_key, agent_name)
            row = connection.execute(
                "SELECT * FROM requests WHERE request_id = ? AND project_key = ?",
                (request_id, project_key),
            ).fetchone()
            if row is None:
                raise BridgeError(f"request '{request_id}' was not found")
            if row["to_agent"] != agent_name:
                raise BridgeError("only the addressed agent can reply to this request")
            if row["status"] in TERMINAL_STATUSES:
                raise BridgeError(f"request is already {row['status']}")
            connection.execute(
                """
                UPDATE requests
                SET status = 'replied', response = ?, replied_at = ?, delivery_lease_until = NULL
                WHERE request_id = ?
                """,
                (message, now, request_id),
            )
            connection.execute(
                "UPDATE agents SET last_seen_at = ? WHERE project_key = ? AND agent_name = ?",
                (now, project_key, agent_name),
            )
            connection.commit()
        return self.get_request(request_id)

    def cancel_request(
        self, project_key: str, agent_name: str, request_id: str, reason: str = ""
    ) -> RequestRecord:
        project_key = validate_project_key(project_key)
        agent_name = validate_agent_name(agent_name)
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM requests WHERE request_id = ? AND project_key = ?",
                (request_id, project_key),
            ).fetchone()
            if row is None:
                raise BridgeError(f"request '{request_id}' was not found")
            if row["from_agent"] != agent_name:
                raise BridgeError("only the requesting agent can cancel this request")
            if row["status"] not in TERMINAL_STATUSES:
                response = reason.strip() or "Cancelled by requester"
                connection.execute(
                    """
                    UPDATE requests
                    SET status = 'cancelled', response = ?, cancelled_at = ?,
                        delivery_lease_until = NULL
                    WHERE request_id = ?
                    """,
                    (response, now, request_id),
                )
            connection.commit()
        return self.get_request(request_id)

    def expire_request(self, request_id: str) -> RequestRecord:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            if row is None:
                raise BridgeError(f"request '{request_id}' was not found")
            if row["status"] not in TERMINAL_STATUSES:
                connection.execute(
                    """
                    UPDATE requests
                    SET status = 'expired', response = 'Timed out waiting for reply',
                        cancelled_at = ?, delivery_lease_until = NULL
                    WHERE request_id = ?
                    """,
                    (now, request_id),
                )
            connection.commit()
        return self.get_request(request_id)

    def get_request(self, request_id: str) -> RequestRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            raise BridgeError(f"request '{request_id}' was not found")
        return RequestRecord(
            request_id=row["request_id"],
            project_key=row["project_key"],
            from_agent=row["from_agent"],
            to_agent=row["to_agent"],
            message=row["message"],
            status=row["status"],
            response=row["response"],
            created_at=row["created_at"],
            delivered_at=row["delivered_at"],
            replied_at=row["replied_at"],
        )

    def status(self, project_key: str) -> dict[str, Any]:
        project_key = validate_project_key(project_key)
        with self._connect() as connection:
            agents = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT agent_name, description, registered_at, last_seen_at
                    FROM agents WHERE project_key = ? ORDER BY agent_name
                    """,
                    (project_key,),
                ).fetchall()
            ]
            counts = {
                row["status"]: row["count"]
                for row in connection.execute(
                    """
                    SELECT status, COUNT(*) AS count FROM requests
                    WHERE project_key = ? GROUP BY status
                    """,
                    (project_key,),
                ).fetchall()
            }
        return {"project_key": project_key, "agents": agents, "request_counts": counts}

