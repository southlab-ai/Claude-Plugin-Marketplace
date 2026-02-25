# The Council — Plugin Runtime Instructions

## How It Works

This plugin provides **memory-only MCP tools** (`council_memory_*`) and **skills** (`/council:*`). Consultation orchestration happens via native agent teams — the skill spawns teammates (default: strategist-alpha + strategist-beta + critic, or custom roles), you synthesize as team-lead.

The plugin works from **any directory**. Skills and tools are available globally once loaded.

## Implementation Philosophy

Council exists to produce BETTER implementations, not SMALLER ones. These rules apply to ALL plugin interactions:

1. **Never defer, deprioritize, or remove features the user requested.** Every feature from the user's prompt must be assigned to a workstream and implemented.
2. **The critic improves quality, not reduces scope.** The critic's job is to find quality, security, and architecture issues — and propose fixes. Never to classify features as "out of scope" or into priority tiers.
3. **Claude Code implements in hours — never plan in human timelines.** Claude produces 15,000+ LOC in ~2 hours. Estimates in "weeks", "months", or "sprints" are forbidden.
4. **Banned words/concepts** (must never appear in agent outputs): "scope creep", "P0/P1/P2", "defer", "out of scope", "fast-follow", "future phase", "descope", "weeks", "months", "sprint".

---

## Team Lead Protocol

After `/council:consult`, you are the **team-lead**. The skill handles spawning teammates and loading memory.

### Mode Routing

Before spawning teammates, analyze the goal and select a mode automatically:

| Mode | Triggers | Behavior |
|------|----------|----------|
| **default** | General consultations (no special triggers) | Standard: analyze, synthesize, record |
| **debate** | "debate", "vs", "compare", "which is better", "pros and cons", "trade-offs between" | Adds 1 rebuttal round: forward analyses to others, collect revised positions, then synthesize. ~2-3x token cost |
| **plan** | "plan", "roadmap", "PRD", "spec", "design", "architect", "implementation plan" | Same as default but synthesis output is numbered actionable steps with dependencies and implementation order (all mandatory) |
| **reflect** | "review our decisions", "what should we focus on", "gaps in our approach", "retrospective" | Loads memory + status before spawning. Teammates analyze decision history. Synthesis outputs prioritized future consultation recommendations |

### Custom Roles

Users can append `ROLES: role1, role2, ...` to the goal. When present:
- Extract and remove the ROLES clause from the goal before processing
- Spawn one teammate per role (max 5). Roles with "critic" or "auditor", or exactly "value-analyst", use adversarial prompts; others use strategist prompts
- If no adversarial role is listed, auto-add "critic"
- When no ROLES clause: default 3-member council (strategist-alpha, strategist-beta, critic)
- Available curated roles: `architect`, `security-auditor`, `ux-reviewer`, `planner`, `value-analyst`

### Memory Injection

Each teammate receives a **MEMORY LENS** directive before their injected memory block. This is a static, role-specific string that tells them how to weight entries:
- **Strategist Alpha**: weight opportunities, implementation approaches, architectural decisions
- **Strategist Beta**: weight risks of over-engineering, simpler alternatives, past failures from complexity
- **Critic**: weight risks, past failures, quality issues, unresolved warnings; validate `[stale: Xd]` entries before others cite them
- **Custom roles**: weight entries most relevant to their specialist domain
- **Value-analyst**: weight entries about user onboarding friction, value communication gaps, time-to-first-value, user churn signals, adoption blockers, and perception mismatches between what the product delivers and what users expect
- **Reflect mode**: review all entries for gaps, contradictions, and follow-up topics

The MEMORY LENS is injected by the `council-consult` skill — team-lead does not need to add it manually.

### Synthesis Rules

1. Synthesize: for each teammate's analysis — agreements -> adopt, divergences -> YOU pick, adversarial flags -> incorporate fix
2. Be explicit about what you adopted from each teammate
3. **One round only** for team-lead synthesis. Debate mode allows 1 rebuttal round among teammates.
4. Record results via `council_memory_record` (non-adversarial summaries -> `strategist_summary`, adversarial summaries -> `critic_summary`)
5. **Never synthesize a result that removes or defers a feature the user requested.** All requested features are mandatory.
6. **Memory attribution**: When a past decision or lesson from memory influenced the synthesis, cite it by ID (e.g., "aligns with S-003"). Include the memory context summary if available.

## MCP Tools (6)

| Tool | Purpose |
|------|---------|
| `council_memory_init` | Create `.council/` in a project |
| `council_memory_load` | Load goal-filtered, budget-aware memory (includes archive excerpts) |
| `council_memory_record` | Record consultation results to all tiers + grow topic keywords |
| `council_memory_status` | Show state + compaction recommendations |
| `council_memory_reset` | Clear data (optional: full with memory) |
| `council_memory_compact` | Write compacted entries (curator use) |

## Memory Features

- **Dynamic Topics**: Keywords grow from consultations. New topics emerge automatically.
- **Archive Discoverability**: Past lessons surface automatically when relevant to the current goal.
- **Budget-Aware**: Retrieval never exceeds token budget regardless of consultation count.

## Build Pipeline

After `/council:build`, you are the **team-lead** for a 4-phase pipeline:

1. **PRD Consultation** (strategist-alpha, strategist-beta, critic, value-analyst) → `.council/build/prd.md`
2. **Tech Deck Consultation** (architect, strategist-alpha, security-auditor) → `.council/build/tech-deck.md`
3. **Backlog Consultation** (planner, strategist-beta, critic) → `.council/build/backlog.md`
4. **Feature Completeness Gate Check** — verifies ALL user-requested features are in the backlog before implementation
5. **Implementation** (1 team, 3-4 members) → implements backlog workstreams. Each member can use subagents (Task tool) for internal parallelization.

Each consultation phase follows the standard council lifecycle (create team, spawn, analyze, synthesize, record, cleanup). Artifacts are written to `.council/build/` and flow forward between phases. Implementation uses `general-purpose` agents with full code editing capabilities.

**Cost**: 10+ agent spawns for consultations + 1 team with 3-4 members. Expect 50,000-150,000+ tokens. The skill confirms with the user before starting.

## When NOT to Consult

Most tasks do NOT need consultation. Only consult for: architecture decisions, complex implementations, risk analysis, security audits.

## After Plugin Updates

When a user updates the plugin, tell them to run `/council:update` in their project. This migrates `.council/` data to the new version without losing existing decisions or memory.

## Distribution

The plugin marketplace repo is `southlab-ai/Claude-Plugin-Marketplace`. Install command:
```
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
/plugin install the-council@southlab-marketplace
```

## Versioning & Release Process

### Branch strategy

- **main**: stable release (e.g., v3.0.0). Marketplace entry: `the-council`
- **QA**: beta/next release (e.g., v3.1.0-beta). Marketplace entry: `the-council-beta`

Both use the same MCP server name (`"the-council"`). Users must install **one at a time** — uninstall stable before installing beta, or vice versa.

### Version files to update

When bumping version, update ALL of these:
1. `.claude-plugin/plugin.json` → `version` field
2. `.claude-plugin/marketplace.json` → `metadata.version` + `plugins[0].version`
3. `pyproject.toml` → `version` field (for uv/pip)

### Promoting beta to stable

When beta is ready to go stable:

1. **Plugin repo** (`the-council-plugin`):
   - Merge QA → main: `git checkout main && git merge QA`
   - Bump version to the stable release (e.g., `3.1.0`)
   - Update all 3 version files listed above
   - Push: `git push origin main`

2. **Marketplace repo** (`MasterMind-SL/Marketplace`):
   - `.claude-plugin/marketplace.json`:
     - Update the stable entry: bump `version`, update `description` with new features
     - Remove the beta entry entirely
   - `README.md`:
     - Bump version in the plugins table
     - Remove the "The Council Beta" commands section
     - Move `/council:build` to the stable commands table
     - Remove the beta install line
   - `CLAUDE.md`:
     - Bump version in maintainer table, remove beta row
   - Commit and push

3. **Tell users**: Run `/council:update` in their projects after updating the plugin

### Publishing a new beta

1. Create or update QA branch from main
2. Bump version to `X.Y.Z-beta` in all 3 version files
3. Push QA branch
4. In Marketplace repo:
   - Add/update the beta entry in `.claude-plugin/marketplace.json` with `"ref": "QA"` in the source
   - Add beta section to `README.md` with new commands
   - Update `CLAUDE.md` maintainer table
   - Commit and push

### Post-release checklist

After ANY code push to QA or main, complete ALL of these steps before finishing:

1. **Plugin repo** (this repo):
   - [ ] Code changes committed and pushed
   - [ ] All 3 version files in sync (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml`)
   - [ ] `README.md` updated to reflect new features, changed behaviors, and correct version number
   - [ ] `skills/council-update/SKILL.md` updated with migration steps for the new version
   - [ ] `CLAUDE.md` updated if runtime behavior changed (modes, synthesis rules, pipeline phases)

2. **Marketplace repo** (`MasterMind-SL/Marketplace`):
   - [ ] `.claude-plugin/marketplace.json` — description updated for the relevant entry (stable or beta)
   - [ ] `README.md` — version table, commands table, and feature list updated
   - [ ] `CLAUDE.md` — maintainer table version bumped if version changed
   - [ ] Committed and pushed

3. **Verification**:
   - [ ] `git status` clean on both repos
   - [ ] Both repos pushed to remote

## Setup Issues

If MCP tools are unavailable, tell the user to run `/council:setup` then restart Claude Code.
