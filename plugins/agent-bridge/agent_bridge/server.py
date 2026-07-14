from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from .store import BridgeError, BridgeStore, validate_timeout


mcp = FastMCP(
    "agent-bridge",
    instructions=(
        "Coordinate independent chats through blocking request/reply calls. "
        "Register each chat first. A receiver waits with listen; a sender calls ask and "
        "remains blocked until the receiver calls reply. Preserve request_id exactly."
    ),
)
store = BridgeStore()


def _error_payload(error: BridgeError) -> dict[str, Any]:
    return {"status": "error", "error": str(error)}


@mcp.tool()
def register_agent(
    project_key: str,
    agent_name: str,
    description: str = "",
) -> dict[str, Any]:
    """Register or refresh this chat's stable identity before calling other tools."""
    try:
        return store.register_agent(project_key, agent_name, description)
    except BridgeError as error:
        return _error_payload(error)


@mcp.tool()
async def listen(
    project_key: str,
    agent_name: str,
    timeout_seconds: int = 3600,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Block this chat's current turn until another agent sends a request.

    When a request arrives, return its request_id, sender, and message. The model should
    answer with reply using the exact request_id, then call listen again if it should stay
    available. An idle timeout is normal and does not create another user turn.
    """
    try:
        timeout_seconds = validate_timeout(timeout_seconds)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            request = store.claim_request(project_key, agent_name, lease_seconds)
            if request is not None:
                payload = request.as_dict()
                payload["instruction"] = (
                    "Process this message, then call reply with this exact request_id."
                )
                return payload
            if asyncio.get_running_loop().time() >= deadline:
                return {
                    "status": "idle",
                    "project_key": project_key,
                    "agent_name": agent_name,
                    "message": "No request arrived before the listen timeout.",
                }
            await asyncio.sleep(0.25)
    except BridgeError as error:
        return _error_payload(error)


@mcp.tool()
async def ask(
    project_key: str,
    from_agent: str,
    to_agent: str,
    message: str,
    timeout_seconds: int = 3600,
) -> dict[str, Any]:
    """Send a request and block this same turn until the addressed agent replies.

    This is the subagent-like primitive: do not poll and do not start another turn. The
    tool call stays pending and returns the peer's response when reply is called.
    """
    request = None
    try:
        timeout_seconds = validate_timeout(timeout_seconds)
        request = store.create_request(project_key, from_agent, to_agent, message)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            current = store.get_request(request.request_id)
            if current.status == "replied":
                return current.as_dict()
            if current.status in {"cancelled", "expired"}:
                return current.as_dict()
            if asyncio.get_running_loop().time() >= deadline:
                return store.expire_request(request.request_id).as_dict()
            await asyncio.sleep(0.25)
    except asyncio.CancelledError:
        if request is not None:
            try:
                store.cancel_request(
                    request.project_key,
                    request.from_agent,
                    request.request_id,
                    "The waiting tool call was cancelled",
                )
            except BridgeError:
                pass
        raise
    except BridgeError as error:
        return _error_payload(error)


@mcp.tool()
def reply(
    project_key: str,
    agent_name: str,
    request_id: str,
    message: str,
) -> dict[str, Any]:
    """Reply to a delivered request and immediately release the waiting ask call."""
    try:
        request = store.reply(project_key, agent_name, request_id, message)
        payload = request.as_dict()
        payload["instruction"] = "Reply delivered. Call listen again to remain available."
        return payload
    except BridgeError as error:
        return _error_payload(error)


@mcp.tool()
def cancel_request(
    project_key: str,
    agent_name: str,
    request_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Cancel a request created by this agent if it should no longer wait for a reply."""
    try:
        return store.cancel_request(project_key, agent_name, request_id, reason).as_dict()
    except BridgeError as error:
        return _error_payload(error)


@mcp.tool()
def bridge_status(project_key: str) -> dict[str, Any]:
    """List registered peers and request counts for one isolated bridge project."""
    try:
        return store.status(project_key)
    except BridgeError as error:
        return _error_payload(error)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

