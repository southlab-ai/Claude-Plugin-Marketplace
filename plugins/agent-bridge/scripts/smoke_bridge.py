from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


class MCPClient:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.process: asyncio.subprocess.Process | None = None
        self.reader_task: asyncio.Task[None] | None = None
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.next_id = 1

    async def start(self) -> None:
        env = os.environ.copy()
        env["AGENT_BRIDGE_DB"] = str(self.db_path)
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "agent_bridge.server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self.reader_task = asyncio.create_task(self._read_responses())
        await self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "agent-bridge-smoke", "version": "0.1.0"},
            },
        )
        await self.notify("notifications/initialized", {})

    async def _read_responses(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while line := await self.process.stdout.readline():
            message = json.loads(line)
            request_id = message.get("id")
            if request_id in self.pending:
                self.pending.pop(request_id).set_result(message)

    async def _send(self, message: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        await self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        response = await asyncio.wait_for(future, timeout=15)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.request("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        content = result.get("content", [])
        if not content:
            raise RuntimeError(f"Tool {name} returned no content")
        return json.loads(content[0]["text"])

    async def close(self) -> None:
        if self.process is not None:
            self.process.terminate()
            await self.process.wait()
        if self.reader_task is not None:
            self.reader_task.cancel()


async def smoke() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "bridge.sqlite3"
        architect = MCPClient(db_path)
        reviewer = MCPClient(db_path)
        await architect.start()
        await reviewer.start()
        try:
            tools = await architect.request("tools/list", {})
            names = {tool["name"] for tool in tools["tools"]}
            required = {"register_agent", "listen", "ask", "reply", "bridge_status"}
            if not required.issubset(names):
                raise AssertionError(f"Missing tools: {sorted(required - names)}")

            await architect.call_tool(
                "register_agent",
                {"project_key": "smoke", "agent_name": "architect"},
            )
            await reviewer.call_tool(
                "register_agent",
                {"project_key": "smoke", "agent_name": "reviewer"},
            )

            ask_task = asyncio.create_task(
                architect.call_tool(
                    "ask",
                    {
                        "project_key": "smoke",
                        "from_agent": "architect",
                        "to_agent": "reviewer",
                        "message": "Can you review this design?",
                        "timeout_seconds": 10,
                    },
                )
            )
            incoming = await reviewer.call_tool(
                "listen",
                {
                    "project_key": "smoke",
                    "agent_name": "reviewer",
                    "timeout_seconds": 10,
                },
            )
            if incoming["message"] != "Can you review this design?":
                raise AssertionError(incoming)
            await reviewer.call_tool(
                "reply",
                {
                    "project_key": "smoke",
                    "agent_name": "reviewer",
                    "request_id": incoming["request_id"],
                    "message": "Approved with one minor suggestion.",
                },
            )
            response = await ask_task
            if response["status"] != "replied":
                raise AssertionError(response)
            if response["response"] != "Approved with one minor suggestion.":
                raise AssertionError(response)
            print("PASS: two independent MCP processes completed a blocking round trip")
        finally:
            await architect.close()
            await reviewer.close()


if __name__ == "__main__":
    asyncio.run(smoke())

