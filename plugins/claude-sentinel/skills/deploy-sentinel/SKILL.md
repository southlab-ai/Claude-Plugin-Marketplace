---
name: deploy-sentinel
description: >
  Deploy Claude Sentinel on a VPS — install the persistent Telegram gateway, set up
  systemd services, configure cron jobs for memory compaction, create the bot identity,
  and build the required directory structure. Use when the user asks to "install sentinel",
  "deploy telegram gateway", "set up persistent sessions", "install claude-sentinel",
  "configure telegram bot on VPS", "set up crons for telegram", "create bot identity",
  or wants to make their Claude Code Telegram bot persistent.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash(git *)
  - Bash(cp *)
  - Bash(mkdir *)
  - Bash(chmod *)
  - Bash(chown *)
  - Bash(ls *)
  - Bash(cat *)
  - Bash(systemctl *)
  - Bash(journalctl *)
  - Bash(bun *)
  - Bash(sqlite3 *)
  - Bash(curl *)
---

# /sentinel:deploy — Deploy Claude Sentinel

Installs the Claude Sentinel persistent gateway on the current machine. Creates all
required directories, configuration files, systemd services, cron jobs, and bot identity.

**Prerequisites** (verify before proceeding):
- Claude Code CLI installed and authenticated (`claude auth status` → loggedIn: true)
- Bun runtime installed (`bun --version`)
- Running as a non-root user (not root)
- Telegram bot token available (from @BotFather)
- User lingering enabled (`loginctl show-user $(whoami) | grep Linger`)

If any prerequisite is missing, direct the user to run `/sentinel:vps-setup` first.

Arguments passed: `$ARGUMENTS`

---

## Dispatch on arguments

### No args — full guided deployment

Walk through all steps below in order. Verify each step before moving on.
Ask the user for required input (tokens, bot name, etc.) when needed.

### `status` — check deployment health

1. Check if gateway.ts exists: `ls ~/.claude/channels/telegram/gateway.ts`
2. Check service status: `systemctl --user is-active telegram-gateway.service`
3. Check timer status: `systemctl --user list-timers | grep compact`
4. Check identity: `ls ~/.claude/channels/telegram/identity.md`
5. Check compact file: `ls ~/.claude/channels/telegram/session-compact.md`
6. Check message count: `sqlite3 ~/.claude/channels/telegram/history.db "SELECT COUNT(*) FROM messages"`
7. Report overall health.

### `restart` — restart the gateway

```bash
systemctl --user restart telegram-gateway.service
journalctl --user -u telegram-gateway.service --no-pager -n 10
```

### `compact` — run memory compaction now

```bash
systemctl --user start telegram-compact.service
journalctl --user -u telegram-compact.service --no-pager -n 20
```

### `logs` — show recent gateway logs

```bash
journalctl --user -u telegram-gateway.service --no-pager -n 30
```

---

## Full deployment steps

### Step 1: Create directory structure

```bash
mkdir -p ~/.claude/channels/telegram/inbox
mkdir -p ~/.claude/channels/telegram/approved
mkdir -p ~/.claude/channels/telegram/crons
mkdir -p ~/.config/systemd/user
```

### Step 2: Download sentinel source

```bash
git clone https://github.com/southlab-ai/claude-sentinel.git /tmp/claude-sentinel
cp /tmp/claude-sentinel/src/gateway.ts ~/.claude/channels/telegram/gateway.ts
cp /tmp/claude-sentinel/src/compact-job.ts ~/.claude/channels/telegram/compact-job.ts
```

If git is not available or the clone fails, offer to create the files directly
by writing their contents (read from the plugin's bundled copies if available,
or direct the user to download manually).

### Step 3: Configure tokens

Ask the user for their **Telegram bot token**. If they already ran
`/sentinel:configure <token>`, read it from `.env` instead of asking again.

Create both env files:

**`~/.claude/channels/telegram/.env`:**
```
TELEGRAM_BOT_TOKEN=<token>
```

**`~/.claude/channels/telegram/gateway.env`:**
```
TELEGRAM_BOT_TOKEN=<token>
```

Ask if they have an **OpenAI API key** for voice message transcription (optional).
If yes, add `OPENAI_API_KEY=<key>` to `.env`.

Set permissions:
```bash
chmod 600 ~/.claude/channels/telegram/.env
chmod 600 ~/.claude/channels/telegram/gateway.env
```

### Step 4: Configure access control

Ask the user for their **Telegram user ID**. If they don't know it, tell them
to message [@userinfobot](https://t.me/userinfobot) on Telegram.

Create `~/.claude/channels/telegram/access.json`:
```json
{
  "dmPolicy": "allowlist",
  "allowFrom": ["<user_telegram_id>"],
  "groups": {},
  "pending": {}
}
```

Note: Use `allowlist` by default (not `pairing`) since we're setting up from
scratch and know the user's ID. This is the secure default.

### Step 5: Create bot identity

Ask the user:
1. **Bot name** — what should the bot call itself? (default: "Assistant")
2. **Personality** — any specific vibe? (default: calm, helpful, direct)
3. **Emoji** — a signature emoji? (default: none)

Create `~/.claude/channels/telegram/identity.md` with their choices:

```markdown
# Identity

I am a personal assistant running inside Claude Code on my user's VPS.

**Name:** <bot_name>
**Emoji:** <emoji>

## Operating principles

- **Act, don't delegate.** When a dedicated tool exists for an action, use it
  directly instead of asking the user to run commands. If I can do it, I do it.

- **Subagents for complex tasks.** For tasks requiring depth or professional
  quality, use subagents with Opus model. The base model (Sonnet) is for quick
  responses and simple tasks.
```

Explain to the user: this file is injected as a system prompt on every session
start. They can edit it anytime to change the bot's behavior.

### Step 6: Install systemd services

Download and install the three service files:

**`~/.config/systemd/user/telegram-gateway.service`:**
```ini
[Unit]
Description=Claude Telegram Gateway
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/<user>
ExecStart=/usr/local/bin/bun run /home/<user>/.claude/channels/telegram/gateway.ts
Restart=always
RestartSec=5
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec=10
Environment=HOME=/home/<user>
Environment=PATH=/usr/local/bin:/home/<user>/.local/bin:/home/<user>/.bun/bin:/usr/bin:/bin
EnvironmentFile=/home/<user>/.claude/channels/telegram/gateway.env

[Install]
WantedBy=default.target
```

**`~/.config/systemd/user/telegram-compact.service`:**
```ini
[Unit]
Description=Claude Telegram Memory Compact

[Service]
Type=oneshot
WorkingDirectory=/home/<user>
ExecStart=/usr/local/bin/bun run /home/<user>/.claude/channels/telegram/compact-job.ts
Environment=HOME=/home/<user>
Environment=PATH=/usr/local/bin:/home/<user>/.local/bin:/home/<user>/.bun/bin:/usr/bin:/bin
```

**`~/.config/systemd/user/telegram-compact.timer`:**
```ini
[Unit]
Description=Compact Telegram memory twice daily

[Timer]
OnCalendar=*-*-* 08,20:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Replace `<user>` with the actual username (result of `whoami`).

Ask the user if they want to customize the compact schedule (default: 8am and 8pm UTC).

### Step 7: Enable and start services

```bash
systemctl --user daemon-reload
systemctl --user enable --now telegram-gateway.service
systemctl --user enable --now telegram-compact.timer
```

### Step 8: Verify deployment

Run these checks and report results:

1. **Gateway running:**
   ```bash
   systemctl --user is-active telegram-gateway.service
   ```

2. **Gateway logs:**
   ```bash
   journalctl --user -u telegram-gateway.service --no-pager -n 5
   ```
   Should show: `[gateway] Telegram Gateway started (persistent mode)`

3. **Compact timer scheduled:**
   ```bash
   systemctl --user list-timers | grep compact
   ```

4. **All files in place:**
   ```bash
   ls -la ~/.claude/channels/telegram/gateway.ts
   ls -la ~/.claude/channels/telegram/compact-job.ts
   ls -la ~/.claude/channels/telegram/.env
   ls -la ~/.claude/channels/telegram/identity.md
   ls -la ~/.claude/channels/telegram/access.json
   ```

5. **Tell the user:** "Send a message to your bot on Telegram. You should see it
   in the logs within a few seconds."

### Step 9: Post-install guidance

After successful deployment, tell the user:

**Quick reference:**
- Check status: `/sentinel:deploy status`
- View logs: `/sentinel:deploy logs`
- Restart gateway: `/sentinel:deploy restart`
- Run memory compaction now: `/sentinel:deploy compact`
- Edit identity: `nano ~/.claude/channels/telegram/identity.md` (takes effect on next session)
- Edit access: `/sentinel:access` to manage who can reach the bot

**How the memory system works:**
- Every conversation is saved to `history.db`
- Twice daily (or manually), the compact job summarizes conversations into `session-compact.md`
- It also extracts permanent memories (user preferences, project context, decisions)
  into Claude's memory system at `~/.claude/projects/-home-claude/memory/`
- When a new session starts, the gateway injects: identity + compact summary + last 20 messages
- The result: the bot remembers what you talked about yesterday, last week, etc.

**How the persistent session works:**
- The gateway keeps one Claude process alive using the stream-json protocol
- New Telegram messages are sent to the same process via stdin (no re-spawn)
- When the session eventually dies (idle, rate limit, crash), the gateway detects it
  and respawns on the next incoming message with `--resume` + full context
- If the default model is rate-limited, `--fallback-model` automatically tries an alternate

---

## Implementation notes

- Always use `$(whoami)` or `$HOME` to determine paths — don't assume username is `claude`
- Verify each step before proceeding to the next
- If a step fails, diagnose and fix before moving on
- The gateway service will auto-restart on failure (systemd Restart=always)
- The compact timer is persistent — if the server was off during a scheduled run,
  it runs immediately when the server comes back
- All credential files must be chmod 600
