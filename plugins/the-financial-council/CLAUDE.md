# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Plugin Identity

This is **the-financial-council**, a plugin in the **Southlab AI Marketplace** monorepo.

- Monorepo root: `../../` (contains `.claude-plugin/marketplace.json`)
- This plugin lives at: `plugins/the-financial-council/`
- Plugin manifest: `.claude-plugin/plugin.json` (must be created)

## Marketplace Rules

This plugin must follow the Southlab marketplace structure:

1. **`.claude-plugin/plugin.json`** — Required. Defines name, version, description, author, keywords. See sibling plugins (`plugins/the-council/`, `plugins/upwork-scraper/`, `plugins/computer-vision/`) for examples.
2. **Version sync** — When bumping the version, update both `.claude-plugin/plugin.json` here AND the matching entry in the monorepo's `.claude-plugin/marketplace.json`.
3. **Single commit** — Plugin code changes + version bumps + marketplace registry update should land in one commit.

## Validation

From the monorepo root:
```
claude plugin validate .
```

## Local Testing

From the monorepo root:
```
/plugin marketplace add ./path/to/monorepo
/plugin install the-financial-council@southlab-marketplace
```
