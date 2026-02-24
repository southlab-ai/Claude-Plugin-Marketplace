# The Council v3.1.0-beta - Claude Code Plugin

Adversarial consultation with **persistent memory** for Claude Code agent teams. Spawn configurable teammates (default: 2 strategists + 1 quality engineer, or custom roles), auto-route between 4 consultation modes, and build project memory that makes consultation #50 smarter than #1.

**v3.1.0-beta**: Anti-deferral system ensures 100% of requested features are implemented. Feature completeness gate check. Claude Velocity context across all agents.

## Features

- **4 Consultation Modes** — Auto-routed: default, debate (with rebuttals), plan (actionable steps), reflect (decision review)
- **Configurable Roles** — Use default 3-member council or specify custom roles (architect, security-auditor, ux-reviewer, planner, or your own)
- **Native Agent Teams** — Teammates run as native Claude Code agents (no subprocess hacks)
- **Three-Tier Memory** — Index (always loaded) + Active (budget-aware) + Archive (auto-surfaced)
- **Dynamic Topics** — Keywords grow organically from consultations; new topics emerge automatically
- **Archive Discoverability** — Past lessons surface automatically when relevant to current goals
- **O(1) Context Cost** — Memory retrieval is budget-capped regardless of consultation count
- **Goal-Aware Retrieval** — Memory filters by relevance to the current goal, not blind dumps
- **Zero Dependencies for Retrieval** — No embeddings, no vector DB, no API calls
- **Plug and Play** — Install, init, consult. No config needed. Clean uninstall.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) v1.0.33+
- Agent teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Quick Start

### 1. Install the plugin

Inside Claude Code:

```
/plugin marketplace add MasterMind-SL/Marketplace
/plugin install the-council@the-council-plugin
```

### 2. Restart Claude Code

Close and reopen. The plugin loads globally — works from **any directory**.

### 3. Install dependencies

```
/council:setup
```

This installs Python packages and verifies the MCP server. **Restart Claude Code again** after setup.

### 4. Initialize in your project

```
/council:init
```

Creates `.council/memory/` with the three-tier memory structure.

### 5. Start consulting

```
/council:consult Should we use PostgreSQL or MongoDB for our event sourcing system?
```

## Usage

8 slash commands:

| Command | Description |
|---------|-------------|
| `/council:setup` | Install dependencies, verify MCP server |
| `/council:init` | Initialize `.council/` in the current project |
| `/council:consult <goal>` | Adversarial consultation (auto-routed mode, optional custom roles) |
| `/council:build <goal>` | Full build pipeline: 3 consultations (PRD, tech deck, backlog) + feature gate + implementation |
| `/council:status` | View decisions, memory health, compaction recommendations |
| `/council:maintain` | Compact memory using the curator agent |
| `/council:update` | Migrate council data after a plugin update |
| `/council:reset` | Clear session data (add `--all` to also clear memory) |

### Example workflow

```
> /council:init

Council initialized at .council/.
Created: .council/memory/ (index.json, decisions.md, lessons.jsonl, role logs)

> /council:consult Should we migrate from REST to GraphQL for our mobile API?

Loading memory (3 consultations, budget: 4000 tokens)...
Spawning strategist-alpha + strategist-beta + critic as teammates...

### Strategist Alpha (ambitious)
Full GraphQL migration: reduces over-fetching, single endpoint,
type-safe schema. Push for complete rewrite with phased rollout...

### Strategist Beta (pragmatic)
GraphQL gateway in front of existing REST. Minimal risk, incremental
adoption. Keep REST for internal services, GraphQL for mobile clients...

### Critic Analysis
Caching harder with GraphQL (no HTTP cache for POST). N+1 query problem.
Authorization complexity increases. Recommends: start with gateway...

### Team Lead Synthesis
Adopted Beta's gateway approach with Alpha's phased timeline.
Critic's caching concern addressed with persisted queries.
Recorded to memory with importance 7.

> /council:status

Consultations: 4 | Memory: healthy
Recent: S-004 GraphQL gateway approach, S-003 PgBouncer pooling...
```

## Consultation Modes

The team-lead automatically selects a mode based on goal text. No flags needed — just use `/council:consult`.

| Mode | When it activates | What changes |
|------|-------------------|--------------|
| **default** | General consultations | Standard flow: teammates analyze in parallel, team-lead synthesizes |
| **debate** | "compare", "vs", "which is better", "pros and cons", "trade-offs between" | Adds 1 rebuttal round — teammates see each other's positions and revise before synthesis. ~2-3x token cost |
| **plan** | "plan", "roadmap", "PRD", "spec", "design", "architect", "implementation plan" | Synthesis formatted as numbered actionable steps with dependencies and implementation order (all mandatory) |
| **reflect** | "review our decisions", "retrospective", "what should we focus on", "gaps in our approach" | Loads memory + status. Teammates analyze decision history. Synthesis outputs prioritized future consultation recommendations |

### Examples

```
# Default mode — general architecture question
/council:consult Should we use PostgreSQL or MongoDB for our event sourcing system?

# Debate mode — triggered by "vs" / "compare"
/council:consult Compare server-side rendering vs client-side rendering for our dashboard

# Plan mode — triggered by "roadmap" / "implementation plan"
/council:consult Create an implementation plan for migrating to microservices

# Reflect mode — triggered by "review our decisions"
/council:consult Review our decisions and identify gaps in our approach
```

## Custom Roles

By default, `/council:consult` spawns 3 teammates: strategist-alpha (ambitious), strategist-beta (pragmatic), and critic (adversarial). You can override this by appending `ROLES:` to the goal.

```
/council:consult Should we add real-time features? ROLES: architect, security-auditor, critic
```

### Rules

- Max 5 teammates per consultation
- If no adversarial role (critic or auditor) is listed, one is auto-added
- Non-matching role names get a generic specialist prompt
- Works with all consultation modes (default, debate, plan, reflect)

### Curated Roles

| Role | Focus |
|------|-------|
| `architect` | System design, scalability, component boundaries |
| `security-auditor` | Threat modeling, vulnerabilities, compliance (adversarial) |
| `ux-reviewer` | User experience, accessibility, interaction patterns |
| `planner` | Workstreams, dependencies, sequencing, integration checkpoints |

You can also use any custom name (e.g., `data-engineer`, `devops-lead`). Custom names get a generic specialist prompt based on the role name.

## Build Pipeline

`/council:build` chains 3 sequential council consultations followed by implementation with 1 dev team (3-4 members). It automates the full product development lifecycle from idea to working code.

```
/council:build A real-time collaborative markdown editor with presence indicators
```

### Phases

| Phase | Roles | Output |
|-------|-------|--------|
| 1. PRD | strategist-alpha, strategist-beta, critic | `.council/build/prd.md` |
| 2. Tech Deck | architect, strategist-alpha, security-auditor | `.council/build/tech-deck.md` |
| 3. Backlog | planner, strategist-beta, critic | `.council/build/backlog.md` |
| 3.5 Feature Gate | team-lead | Verifies 100% feature coverage |
| 4. Implementation | 1 team (3-4 members) | Working code |

Each consultation phase follows the standard council lifecycle. Artifacts flow forward: the PRD feeds the tech deck, both feed the backlog, and the backlog drives implementation.

### Anti-deferral system

The build pipeline enforces full feature implementation:
- **No priority tiers** — All features from the user prompt are mandatory (no P0/P1/P2)
- **Claude Velocity** — Agents plan for Claude speed (~2 hours), not human timelines
- **Quality Engineer** — The critic improves implementations, never cuts scope
- **Feature Gate** — Between backlog and implementation, verifies every requested feature is assigned

### Implementation phase

The team-lead:
1. Executes foundation tasks (project setup, shared types)
2. Spawns 1 team with 3-4 developer members
3. Members implement their workstreams (can use subagents for internal parallelization)
4. Team-lead coordinates integration checkpoints and handles blockers
5. Post-integration: wires everything together, runs tests

### Flow

```
User: /council:build "goal"
        |
        v
    Phase 1: PRD Consultation (3 agents)
    → writes .council/build/prd.md → records to memory
        |
        v
    Phase 2: Tech Deck Consultation (3 agents)
    → reads prd.md → writes .council/build/tech-deck.md → records to memory
        |
        v
    Phase 3: Backlog Consultation (3 agents)
    → reads prd.md + tech-deck.md → writes .council/build/backlog.md → records to memory
        |
        v
    Phase 3.5: Feature Completeness Gate Check
    → compares original prompt vs backlog → fixes any gaps
        |
        v
    Phase 4: Implementation (1 team, 3-4 members)
    → reads all artifacts → foundation tasks → workstreams → post-integration
    → records to memory (pinned)
```

> **Warning**: This is token-intensive (~50,000-150,000+ tokens). The skill confirms with the user before starting. Recommended for greenfield features or major redesigns.

## How It Works

```
User: /council:consult "goal"
        |
        v
    Skill expands protocol
        |
        v
    Team-lead (main Claude session):
    1. Verify .council/ exists
    2. Route mode (analyze goal → default/debate/plan/reflect)
    3. council_memory_load()  --> MCP returns budget-aware memory + archive excerpts
       (reflect mode also loads council_memory_status)
    4. TeamCreate("council")  --> creates native agent team
    5. Task(teammates) [PARALLEL]  --> default: strategist-alpha, strategist-beta, critic
       (custom ROLES: one teammate per role, max 5, adversarial auto-added)
    6. Receives analyses via SendMessage from all teammates
       (debate mode: forward analyses → 1 rebuttal round → revised positions)
    7. Synthesizes (agree/diverge/critique → adopt/resolve/incorporate)
       (plan mode: numbered steps, all mandatory, with implementation order)
       (reflect mode: prioritized future consultation recommendations)
    8. council_memory_record() --> MCP persists to all tiers + grows topic keywords
    9. shutdown_request to all --> TeamDelete --> Presents to user (includes mode used)
```

The MCP server handles **memory persistence only** (6 tools). Orchestration is done by the skill using native Claude Code agent teams — no subprocess management, no temp files, no Windows hacks.

## Agents

### Default council (no ROLES clause)

| Agent | Role | How it runs |
|-------|------|-------------|
| `strategist` (x2) | Alpha: ambitious, forward-thinking. Beta: pragmatic about quality, not scope. | Native teammates via Task tool |
| `critic` | Quality engineering: architecture risks, security gaps, implementation improvements | Native teammate via Task tool |

### Custom roles (via ROLES clause)

| Agent | Role | How it runs |
|-------|------|-------------|
| `architect` | System design, scalability, component boundaries | Native teammate via Task tool |
| `security-auditor` | Threat modeling, vulnerabilities, compliance (adversarial) | Native teammate via Task tool |
| `ux-reviewer` | User experience, accessibility, interaction patterns | Native teammate via Task tool |
| `planner` | Workstreams, dependencies, sequencing, integration checkpoints | Native teammate via Task tool |

### Maintenance

| Agent | Role | How it runs |
|-------|------|-------------|
| `curator` | Memory compaction: deduplicate, score, prune entries | Subagent via Task tool |

## Memory System

Three-tier, budget-aware memory:

| Tier | Purpose | Files | Size |
|------|---------|-------|------|
| **0: Index** | Always loaded — consultation count, recent decisions, pinned items, topic index | `index.json` | ~200-500 tokens |
| **1: Active** | Budget-aware — scored, tagged, goal-filtered entries | `{role}-active.json` | ~1,000-4,000 tokens |
| **2: Archive** | Auto-surfaced when relevant — append-only logs, lessons, decision history | `{role}-log.md`, `decisions.md`, `lessons.jsonl` | Unbounded |

### Scalability

| Consultations | Tokens loaded (4k budget) | vs v1 system |
|--------------|--------------------------|-------------|
| 10 | ~1,100 | 6.5x less |
| 50 | ~2,900 | 8x less |
| 100 | ~4,000 (budget cap) | 9x less |
| 500 | ~4,000 (budget cap) | 36x less |

Memory retrieval uses **keyword + topic matching** (10 seed categories + dynamic topics that grow from consultations, zero dependencies). When a goal matches archived topics, relevant lessons are automatically surfaced within the token budget. Importance scoring combines base importance, recency bonus, reference count, and staleness penalty.

**Retrieval improvements (v3.1.0-beta):**
- **Synonym expansion** — `extract_topics()` maps 50+ synonyms to canonical keywords (e.g. `autoscaling` → `performance`, `postgres` → `database`) and extracts bigrams, so topic matching works across phrasing variants.
- **Staleness markers** — entries older than 90 days display `[stale: Xd]` and score 0.7× in relevance. Pinned entries are always exempt.
- **3-tier packing** — `build_memory_response()` adapts detail to budget: generous (≥2500 tokens remaining) uses full text; normal (800–2500) emits one-liners then upgrades top entries to full text; tight (<800) uses one-liners only.
- **Archive top-12 by relevance** — archive excerpts now select the top-12 most relevant lessons (was last-5 by recency), with a 200-lesson scan cap and 600-token archive budget cap.
- **MEMORY LENS directives** — each teammate receives a role-specific lens before the injected memory block, guiding them to weight entries most relevant to their perspective (e.g. strategist weights opportunities; critic weights risks and stale entries).

### Compaction

When active memory exceeds thresholds, `/council:maintain` spawns the curator agent to:
- Deduplicate entries across sessions
- Lower importance of superseded decisions
- Merge related insights
- Reduce detail levels (full -> summary -> headline)

The curator runs in its own context window — zero cost to your main session.

## MCP Tools

| Tool | Purpose |
|------|---------|
| `council_memory_init` | Create `.council/` directory structure |
| `council_memory_load` | Load goal-filtered, budget-aware memory |
| `council_memory_record` | Record consultation results to all tiers |
| `council_memory_status` | Show state + compaction recommendations |
| `council_memory_reset` | Clear data (optional: full with memory) |
| `council_memory_compact` | Write compacted entries (curator use) |

## Plugin Structure

```
the-council-plugin/
├── .claude-plugin/
│   ├── plugin.json            # Manifest
│   └── marketplace.json       # Distribution
├── .mcp.json                  # MCP server config
├── src/
│   ├── __init__.py
│   ├── __main__.py            # Entry: python -m src.server
│   ├── server.py              # FastMCP — 6 memory tools
│   ├── memory.py              # Memory engine (retrieval, scoring, indexing)
│   └── config.py              # get_plugin_root()
├── agents/
│   ├── strategist.md          # Teammate: forward-thinking analysis
│   ├── critic.md              # Teammate: adversarial analysis
│   ├── architect.md           # Teammate: system design analysis
│   ├── security-auditor.md    # Teammate: adversarial security analysis
│   ├── ux-reviewer.md         # Teammate: UX and accessibility analysis
│   ├── planner.md             # Teammate: execution planning
│   └── curator.md             # Subagent: memory compaction
├── skills/
│   ├── council-build/         # BUILD PIPELINE (3 consultations + parallel implementation)
│   ├── council-consult/       # THE ORCHESTRATOR
│   ├── council-init/
│   ├── council-status/
│   ├── council-maintain/
│   ├── council-reset/
│   ├── council-setup/
│   └── council-update/          # Migration after plugin updates
├── CLAUDE.md                  # Runtime instructions only
├── pyproject.toml
└── uv.lock
```

## Installation Options

### Option 1: Marketplace (recommended)

See [Quick Start](#quick-start) above.

### Option 2: From source

```bash
git clone https://github.com/MasterMind-SL/the-council-plugin
cd the-council-plugin
uv sync
claude --plugin-dir .
```

### Option 3: Team marketplace

Add to your project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "the-council-plugin": {
      "source": {
        "source": "github",
        "repo": "MasterMind-SL/the-council-plugin"
      }
    }
  },
  "enabledPlugins": {
    "the-council@the-council-plugin": true
  }
}
```

## Upgrading

After updating the plugin to a new version, run in each project that has `.council/`:

```
/council:update
```

This migrates your existing council data (decisions, lessons, memory) to the new version without losing anything. It also reports what's new.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Skills run but Claude tries wrong approaches | MCP server not connected. Run `/council:setup`, restart Claude Code |
| "Council not initialized" | Run `/council:init` in your project |
| Teammates don't spawn | Enable agent teams: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |
| Memory seems empty after many consultations | Run `/council:status` to check health, `/council:maintain` if needed |

## Development

```bash
# Install dependencies
uv sync

# Run MCP server standalone
uv run python -m src.server

# Verify tools register (should show 6)
uv run python -c "from src.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
```

## License

MIT
