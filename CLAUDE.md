# Southlab AI Marketplace — Maintainer Instructions

## Structure

This is a **monorepo marketplace**. All plugins live under `plugins/` as subdirectories:

| Plugin | Path | Current Version |
|--------|------|-----------------|
| upwork-scraper | `plugins/upwork-scraper/` | 0.2.0 |
| the-council | `plugins/the-council/` | 3.1.0 |
| computer-vision | `plugins/computer-vision/` | 1.6.0 |

The marketplace registry is at `.claude-plugin/marketplace.json`.

## When Updating a Plugin

Since plugins live in this repo, updating is straightforward:

1. Make changes to the plugin code in `plugins/<plugin-name>/`
2. Bump the version in **both**:
   - `plugins/<plugin-name>/.claude-plugin/plugin.json`
   - `.claude-plugin/marketplace.json` (the matching plugin entry)
3. Update `README.md` version table if changed
4. Commit and push — one commit, everything stays in sync

## When Adding a New Plugin

1. Create the plugin directory under `plugins/<plugin-name>/`
2. Add `.claude-plugin/plugin.json` inside it
3. Add a new entry to the `plugins` array in `.claude-plugin/marketplace.json`
4. Add the plugin to the README table and commands section
5. Commit and push

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
