# Southlab AI Marketplace — Maintainer Instructions

## Structure

This is a **monorepo marketplace**. All plugins live under `plugins/` as subdirectories:

| Plugin | Path | Current Version |
|--------|------|-----------------|
| agent-bridge | `plugins/agent-bridge/` | 0.1.0 |
| upwork-scraper | `plugins/upwork-scraper/` | 0.2.0 |
| the-council | `plugins/the-council/` | 3.2.0 |
| computer-vision | `plugins/computer-vision/` | 2.6.0 |
| ultracodex | `plugins/ultracodex/` | 1.0.0 |
| claude-sentinel | `plugins/claude-sentinel/` | 0.1.0 |
| kg-educacion | `plugins/kg-educacion/` | 3.1.0 |

The marketplace registry is at `.claude-plugin/marketplace.json`.

### Prototypes — not published

- `plugins/the-financial-council/` — unpublished research prototype; not installable

## When Updating a Plugin

Since plugins live in this repo, updating is straightforward:

1. Make changes to the plugin code in `plugins/<plugin-name>/`
2. Bump the version in **all three**:
   - `plugins/<plugin-name>/.claude-plugin/plugin.json`
   - `plugins/<plugin-name>/.codex-plugin/plugin.json` (when present)
   - `.claude-plugin/marketplace.json` (the matching plugin entry)
3. Update `README.md` version table if changed
4. Commit and push — one commit, everything stays in sync

## When Adding a New Plugin

1. Create the plugin directory under `plugins/<plugin-name>/`
2. Add `.claude-plugin/plugin.json` inside it
3. Add at least one real plugin component (skill, command, agent, hook, or MCP server)
4. Only after the manifest and component exist, add a new entry to the `plugins` array in `.claude-plugin/marketplace.json`
5. Add the plugin to the README table and commands section
6. Commit and push

## External PRs

This marketplace is **first-party only**. Reject PRs from external vendors adding plugins that promote their own service (precedent: PR #1, "Add Xquik plugin"). Every plugin entry uses author "Southlab AI" and `repository` pointing at this monorepo. Watch for vendor-PR red flags: auto-enabling their plugin in the README team-config example, and out-of-scope edits to other plugins' registry entries.

## Testing Locally

```
/plugin marketplace add ./path/to/this/repo
/plugin install <plugin-name>@southlab-marketplace
```

## Validation

```
claude plugin validate .
```

## Files

- `.claude-plugin/marketplace.json` — Plugin registry (source of truth)
- `plugins/*/` — Plugin source code
- `README.md` — Public documentation
- `.gitignore` — Excludes build artifacts, .venv, data/, .env, __pycache__
