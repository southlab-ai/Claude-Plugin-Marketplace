# Claude Sentinel Plugin

This plugin provides guided setup skills for deploying Claude Sentinel — a persistent
session supervisor for Claude Code's Telegram channel.

## Skills

- `/sentinel:vps-setup` — Install Claude Code on a VPS (non-root user, auth, bun, lingering)
- `/sentinel:configure` — Save Telegram bot token to .env and gateway.env
- `/sentinel:access` — Manage allowlists, pairing codes, group policies
- `/sentinel:deploy` — Full deployment: gateway, compact job, systemd services, identity, crons

## Key paths

- Gateway: `~/.claude/channels/telegram/gateway.ts`
- Compact job: `~/.claude/channels/telegram/compact-job.ts`
- Bot identity: `~/.claude/channels/telegram/identity.md`
- Access control: `~/.claude/channels/telegram/access.json`
- Tokens: `~/.claude/channels/telegram/.env` (chmod 600)
- Services: `~/.config/systemd/user/telegram-gateway.service`
- Compact timer: `~/.config/systemd/user/telegram-compact.timer`

## Important

- Never run as root — Claude Code blocks --dangerously-skip-permissions as root
- Always use allowlist policy in production (pairing is temporary)
- The gateway uses --fallback-model for automatic model switching on rate limits
- Compact job runs twice daily and extracts permanent memories
