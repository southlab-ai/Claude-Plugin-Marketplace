---
name: council-update
description: Migrate council data after a plugin update. Handles version transitions and schema changes.
---

# Update Council

Run this after updating The Council plugin to a new version. Migrates `.council/` data and reports what's new.

## Step 1: Check initialization

Check if `.council/` exists in the current project directory. If not, tell the user: "No council found. Run `/council:init` to start fresh." and stop.

## Step 2: Read current version

Read `.council/memory/index.json`. Check for the `plugin_version` field:
- If `plugin_version` exists: that's the installed version.
- If `plugin_version` is missing: this is a **pre-v3.0.0 installation** (v2.x or earlier).

## Step 3: Run migrations

### From v2.x (no plugin_version) to v3.0.0

1. **Add version tracking**: Add `"plugin_version": "3.0.0"` to `index.json` and save it.

2. **Preserve all existing data**: Do NOT delete or modify existing decisions, lessons, active memory, or archives. All v2.x memory is fully compatible with v3.0.0.

3. **Report what's new in v3.0.0**:
   - 4 consultation modes (default, debate, plan, reflect) — auto-routed, no flags needed
   - Configurable roles via `ROLES:` clause (architect, security-auditor, ux-reviewer, planner, or custom)
   - Debate mode with 1 rebuttal round (teammates cross-read positions)
   - Plan mode outputs numbered actionable steps (all mandatory)
   - Reflect mode analyzes your decision history and recommends future consultations
   - "Hub" renamed to "team-lead" in all protocols and documentation

### From v3.0.0 to v3.1.0-beta

1. **Add `original_prompt` field**: Read `index.json`, add `"original_prompt": ""` if missing, save it.

2. **Preserve all existing data**: Do NOT delete or modify existing decisions, lessons, active memory, or archives. All v3.0.0 memory is fully compatible with v3.1.0-beta.

3. **Update plugin_version**: Set `"plugin_version": "3.1.0-beta"` in `index.json` and save.

4. **Report what's new in v3.1.0-beta**:
   - **Anti-deferral system**: Agents never cut, defer, or deprioritize features. Everything the user asks for gets implemented.
   - **Quality Engineer critic**: The critic now improves quality (security, architecture, error handling) instead of managing scope. Never classifies features into priority tiers.
   - **Claude Velocity**: All agents understand that Claude Code implements in ~2 hours, not weeks. No human timeline estimates.
   - **Feature completeness gate**: `/council:build` now runs a gate check between backlog and implementation to verify 100% of requested features are assigned.
   - **Scaled implementation**: Build pipeline uses 1 team with 3-4 members (each can use subagents for internal parallelization).
   - **Original prompt tracking**: Memory stores the original user prompt for feature-tracking throughout the build pipeline.
   - **Plan mode updated**: Outputs implementation order (all mandatory) instead of P0/P1/P2 priorities.
   - **Banned words**: Agent outputs no longer contain "scope creep", "P0/P1/P2", "defer", "out of scope", "fast-follow", "future phase", "descope", "weeks", "months", "sprint".
   - **Consistent banned words**: All 5 agents (strategist, critic, planner, architect, security-auditor) now share the same complete banned words list including "P0/P1/P2" and "Never classify features into priority tiers".

### From v3.1.0-beta (pre-memory-improvements) to v3.1.0-beta (post-memory-improvements)

This is an in-place update within the same version. The schema bumped from v1→v2 with a new `last_validated` field on memory entries.

1. **Auto-migration already applied**: `load_index()` and `load_active()` auto-migrate v1 files to v2 on first read — no manual action needed for existing data.

2. **Verify schema version**: Read each `*-active.json` file in `.council/memory/`. Each should have `"version": 2`. If any still show `"version": 1`, open and resave them (the next council operation will auto-migrate them).

3. **No data loss**: All existing entries are fully compatible. The `last_validated` field defaults to `created` for legacy entries when computing staleness.

4. **Report what's new in this update**:
   - **Synonym expansion**: `extract_topics()` now expands synonyms (e.g. "autoscaling" → "performance", "postgres" → "database") and bigrams, improving topic matching across 50+ synonym pairs.
   - **Staleness markers**: Memory entries older than 90 days show a `[stale: Xd]` indicator. Stale entries score 0.7x in relevance (pinned entries always exempt).
   - **`last_validated` field**: New entries record when they were last validated. Existing entries fall back to `created` date for staleness calculation.
   - **3-tier packing**: `build_memory_response()` adapts detail level to budget — generous (≥2500 tokens remaining): full text; normal (800-2500): one-liners upgraded to full text for top entries; tight (<800): one-liners only.
   - **Archive improvements**: Archive excerpts now select top-12 by relevance (was last-5 by recency), with a 200-lesson scan cap and 600-token budget cap to prevent blowout.
   - **MEMORY LENS directives**: Each teammate in `/council:consult` now receives a role-specific lens directive before the memory block, guiding them to weight entries relevant to their perspective.

### From v3.1.0-beta to v3.1.0-beta (already current, post-memory-improvements)

Report: "Already on the latest v3.1.0-beta. No migration needed." and stop.

### Future migrations (template)

When new versions are released, add migration blocks here:

```
### From vX.Y.Z to vA.B.C
1. <migration step>
2. <migration step>
3. Update plugin_version to "A.B.C" in index.json
```

## Step 4: Verify integrity

After migration, run a quick health check:
1. Call `council_memory_status` with `project_dir`
2. Check that consultation_count, recent_decisions, and memory health look correct
3. If any issues, report them and suggest `/council:reset` (soft) or `/council:init` (fresh start)

## Step 5: Report

Present to the user:
1. Previous version (or "pre-v3.0.0" if no plugin_version was found)
2. Current version after migration
3. What was migrated (list each change)
4. What's new in this version (brief feature summary)
5. Memory health status
6. Next steps: "Run `/council:consult` to use the new features."
