# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Plugin Identity

This is **the-financial-council**, an unpublished prototype in the **Southlab AI Marketplace** monorepo.

- Monorepo root: `../../` (contains `.claude-plugin/marketplace.json`)
- This plugin lives at: `plugins/the-financial-council/`
- It has no plugin manifest or installable plugin surface and is not published in the marketplace.

## Publication Gate

To publish this prototype as a plugin, all of the following must land in the same commit:

1. A `.claude-plugin/plugin.json` manifest.
2. At least one real plugin component (skill, command, agent, hook, or MCP server).
3. Tests covering the installable functionality.
4. A matching entry in the monorepo's `.claude-plugin/marketplace.json`.

Any future published version must be higher than `1.1.0`; reusing `1.1.0` could leave users who cached the empty package on the broken copy.

## Validation

From the monorepo root:
```
claude plugin validate .
```
