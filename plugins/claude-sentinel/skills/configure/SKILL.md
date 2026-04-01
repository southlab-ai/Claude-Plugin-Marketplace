---
name: configure
description: >
  Set up the Telegram channel for Claude Sentinel — save the bot token, review access
  policy, and prepare the gateway environment. Use when the user pastes a Telegram bot
  token, asks to configure Telegram, asks "how do I set this up", or wants to check
  channel status. VPS-aware version with headless guidance.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash(ls *)
  - Bash(mkdir *)
  - Bash(chmod *)
---

# /sentinel:configure — Telegram Channel Setup

Writes the bot token to `~/.claude/channels/telegram/.env` AND
`~/.claude/channels/telegram/gateway.env` (both needed — `.env` for the MCP server,
`gateway.env` for the systemd service). Orients the user on access policy.

Arguments passed: `$ARGUMENTS`

---

## Dispatch on arguments

### No args — status and guidance

Read state files and give the user a complete picture:

1. **Token** — check `~/.claude/channels/telegram/.env` for `TELEGRAM_BOT_TOKEN`.
   Show set/not-set; if set, show first 10 chars masked (`123456789:...`).

2. **Gateway env** — check `~/.claude/channels/telegram/gateway.env` exists and
   matches. Warn if missing or mismatched.

3. **Access** — read `~/.claude/channels/telegram/access.json` (missing file =
   defaults: `dmPolicy: "pairing"`, empty allowlist). Show:
   - DM policy and what it means
   - Allowed senders: count and list
   - Pending pairings: count with codes

4. **Gateway status** — check if `telegram-gateway.service` is running:
   `systemctl --user is-active telegram-gateway.service 2>/dev/null`

5. **What next** — concrete next step based on state:
   - No token → *"Get a token from @BotFather on Telegram (from your phone, not the
     VPS — the VPS has no browser). Then run `/sentinel:configure <token>`."*
   - Token set, nobody allowed → *"DM your bot on Telegram. It replies with a code;
     approve with `/sentinel:access pair <code>`."*
   - Token set, someone allowed, no gateway → *"Run `/sentinel:deploy` to install the
     persistent gateway."*
   - Everything ready → *"Ready. DM your bot to reach the assistant."*

**Push toward lockdown.** Once IDs are captured via pairing, suggest switching to
`allowlist` policy. Pairing is temporary — allowlist is the goal.

### `<token>` — save it

1. Treat `$ARGUMENTS` as the token (trim whitespace). BotFather tokens look like
   `123456789:AAH...` — numeric prefix, colon, long string.
2. `mkdir -p ~/.claude/channels/telegram`
3. Read existing `.env` if present; update/add the `TELEGRAM_BOT_TOKEN=` line,
   preserve other keys (like `OPENAI_API_KEY`). Write back, no quotes around value.
4. Write `gateway.env` with same token (separate file for systemd `EnvironmentFile`).
5. `chmod 600` both files — the token is a credential.
6. Confirm, then show the no-args status so the user sees where they stand.

### `clear` — remove the token

Delete the `TELEGRAM_BOT_TOKEN=` line from `.env` and delete `gateway.env`.

---

## Implementation notes

- The channels dir might not exist if the server hasn't run yet. Missing file = not
  configured, not an error.
- The MCP server reads `.env` once at boot. Token changes need a session restart.
- `access.json` is re-read on every inbound message — policy changes take effect
  immediately.
- On a VPS, remind users that BotFather setup happens on their phone/desktop Telegram,
  not on the server.
- After saving a token, suggest `/sentinel:deploy` if the gateway isn't installed yet.
