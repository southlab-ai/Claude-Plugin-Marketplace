# Agent Bridge

Agent Bridge lets two independent Codex or Claude chats communicate while preserving the
desktop application and each chat's normal capabilities. It adds a local MCP request/reply
channel; it does not add another UI or CLI.

## How it behaves

- The receiver registers and calls `listen`, keeping its current turn active.
- The sender calls `ask`, which remains blocked like a subagent wait.
- The receiver processes the request and calls `reply`.
- The sender's original `ask` returns and the same turn continues.

Each desktop chat launches its normal STDIO MCP process. Processes share only
`~/.agent-bridge/bridge.sqlite3`, with project-scoped identities and requests.

## Install

### Codex Desktop

```bash
codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin add agent-bridge@southlab-marketplace
```

Restart Codex Desktop after installing.

### Claude Code

```text
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
/plugin install agent-bridge@southlab-marketplace
```

Restart Claude Code after installing.

## Use two chats

Receiver:

```text
Use Agent Bridge. Register as reviewer in project checkout-redesign. Wait for architect,
reply to its request, then wait again. Maximum 3 requests.
```

Sender:

```text
Use Agent Bridge. Register as architect in project checkout-redesign. Ask reviewer to inspect
my plan and wait for its response before continuing.
```

Codex and Claude Code can be mixed on the same computer and user account. Both clients must
use the same `project_key`; their `agent_name` values must be different.

## Tools

| Tool | Purpose |
|---|---|
| `register_agent` | Register a chat identity inside a project scope |
| `listen` | Wait for the next request without creating another user turn |
| `ask` | Send a request and block until its reply arrives |
| `reply` | Return a result and release the waiting `ask` |
| `cancel_request` | Cancel a request created by the current agent |
| `bridge_status` | Inspect peers and request counts for a project |

## Local data and privacy

The server opens no network port and sends no telemetry. Messages remain in a SQLite database
under the current user's home directory. Override the location with `AGENT_BRIDGE_DB`.

The bundled launcher supports Codex and Claude Code on macOS and Linux. It resolves either
`PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` before starting the same Python MCP server.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run python scripts/smoke_bridge.py
```
