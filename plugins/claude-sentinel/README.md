# Claude Sentinel Plugin

A Claude Code plugin with guided skills for setting up and deploying [Claude Sentinel](https://github.com/southlab-ai/claude-sentinel) — a session supervisor for Claude Code's Telegram channel.

## What it does

Claude Code's Telegram channel plugin works, but sessions are fragile. When the Claude process exits — idle timeout, rate limit, crash — Telegram goes silent. Claude Sentinel patches these gaps with a persistent gateway, crash recovery, and long-term memory.

This plugin provides 4 skills that guide you through the entire setup:

| Skill | Description |
|-------|-------------|
| `/sentinel:vps-setup` | Step-by-step Claude Code installation on a VPS via SSH |
| `/sentinel:configure` | Telegram bot token setup (VPS-aware, handles headless auth) |
| `/sentinel:access` | Manage who can reach your bot (allowlists, pairing, group policies) |
| `/sentinel:deploy` | Install the persistent gateway, systemd services, cron jobs, and bot identity |

## Install

```bash
# Add the Southlab marketplace (if not already added)
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace

# Install the plugin
/plugin install claude-sentinel@southlab-marketplace
```

## Quick start

```bash
# 1. Set up Claude Code on your VPS
/sentinel:vps-setup

# 2. Configure Telegram bot token
/sentinel:configure <your-bot-token>

# 3. Deploy the persistent gateway
/sentinel:deploy

# 4. Set up access control
/sentinel:access pair <code>
```

## Requirements

- A VPS or server with Linux (Ubuntu/Debian recommended)
- SSH access to the server
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Claude Max or API subscription

## Related

- [Claude Sentinel](https://github.com/southlab-ai/claude-sentinel) — the gateway source code
- [Claude Code Telegram Plugin](https://github.com/anthropics/claude-plugins-official) — the official MCP plugin

## License

MIT
