# Agent Bridge Maintainer Guidance

This plugin must preserve the behavior of the Codex and Claude desktop clients. It adds MCP
tools and a skill; it must not introduce a replacement UI, terminal orchestrator, or external
agent runtime.

## Runtime contract

- `ask` is blocking and returns only after `reply`, cancellation, or timeout.
- `listen` is blocking and returns one leased request at a time.
- Independent MCP processes coordinate only through the shared SQLite database.
- Keep project isolation, recipient validation, cancellation, and delivery leases intact.
- Do not add network listeners or telemetry.

## Verification

Run from this plugin directory:

```bash
uv sync --extra dev
uv run pytest
uv run python scripts/smoke_bridge.py
```

