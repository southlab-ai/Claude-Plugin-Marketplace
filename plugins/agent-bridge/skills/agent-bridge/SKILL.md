---
name: agent-bridge
description: Connect two independent Codex or Claude chats so one can wait synchronously for the other's response. Use whenever the user asks chats, agents, sessions, or threads to talk to each other, register as peers, wait for a peer, send a blocking request, or behave like a subagent across separate chats.
compatibility: Requires the bundled agent-bridge MCP server.
---

# Agent Bridge

Coordinate independent chats while keeping each chat's current turn open. The sender uses
`ask` and resumes when the receiver calls `reply`; do not replace this with polling or a new
user turn.

## Shared identifiers

Before using the bridge, determine:

- `project_key`: a stable shared scope agreed by both chats, such as the repository name or a
  user-provided collaboration name.
- `agent_name`: a unique short identity for this chat, such as `architect` or `reviewer`.

Names use letters, digits, `_`, and `-`. Keep the same identifiers throughout the collaboration.

## Register

Call `register_agent` once at the beginning of the chat's active bridge turn. Include a short
description so peers can distinguish roles. If the other peer is not registered yet, report
that fact and wait for the user to start it; do not invent another identity.

## Receive and remain available

When the user asks this chat to receive work:

1. Register the identity.
2. Call `listen` with a long timeout, normally 3600 seconds.
3. When it returns a request, preserve `request_id` exactly.
4. Complete the requested analysis or work using the chat's normal Codex capabilities.
5. Call `reply` with the result and exact `request_id`.
6. If the user requested persistent availability, call `listen` again in the same turn.

An `idle` result means no request arrived before the timeout. Explain it briefly; do not claim
that the peer answered.

## Ask and wait synchronously

When the user asks this chat to consult another chat:

1. Register the identity if needed.
2. Optionally call `bridge_status` to verify the target name.
3. Call `ask` with the full, self-contained request and a suitable timeout.
4. Remain in the same turn while the tool is pending. Do not poll, schedule a task, or ask the
   user to copy messages.
5. When `ask` returns `replied`, treat `response` as the peer's answer and continue the task.

If `ask` returns `expired` or `cancelled`, state that no usable peer response arrived. Do not
fabricate one.

## Safety and lifecycle

- Limit autonomous dialogue to the number of rounds requested by the user; default to one
  request/reply round when no limit is specified.
- Never send secrets unless the user explicitly placed them in scope for both chats.
- Use distinct project keys for unrelated work.
- Stop listening when the user interrupts the turn.
- Use `cancel_request` only for a request created by this chat.

## Example setup

In the receiver chat:

```text
Use Agent Bridge. Register as reviewer in project checkout-redesign. Wait for architect,
review its proposal, reply with concrete findings, then wait again. Maximum 3 requests.
```

In the sender chat:

```text
Use Agent Bridge. Register as architect in project checkout-redesign. Ask reviewer to inspect
my plan for correctness and wait for its response before continuing.
```

