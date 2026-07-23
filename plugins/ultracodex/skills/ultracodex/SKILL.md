---
name: ultracodex
description: Ultracode-style multi-agent orchestration using a fleet of OpenAI Codex agents (GPT-5.6 family — sol/terra/luna) instead of Claude subagents. Max 10 concurrent agents. Use when the user says "ultracodex" or asks to attack a task exhaustively with parallel Codex/GPT agents — deep audits, broad reviews, migrations, multi-angle research or design. For a single Codex agent, use the codex-agent skill instead.
---

# Ultracodex — Codex fleet orchestration

You (Claude) are the **orchestrator**: decompose, write prompts, spawn, synthesize, decide the next phase. The **workers** are `codex exec` processes (see [[codex-agent]] skill for base conventions). Token cost on the Codex side is billed to the user's own Codex plan and is not your concern — but the concurrency cap is.

## Model & effort per role (GPT-5.6 family)

| Model | Tier | Fleet roles |
|---|---|---|
| `gpt-5.6-luna` | fast | mechanical, well-scoped: extraction, classification, per-file smoke checks |
| `gpt-5.6-terra` | workhorse — **default** | finders, reviewers, 1-vote verifiers, straightforward implementers |
| `gpt-5.6-sol` | flagship | judges, adversarial verifiers on high-severity findings, design proposals, complex implementers |

- **Default: `gpt-5.6-terra` at effort `medium`** unless the table or the user says otherwise.
- Effort values on 5.6: `low | medium | high | xhigh | max` (`max` is new to 5.6; `minimal` is gone).
- Escalate per-agent — `sol` and/or `high`/`xhigh` — when the user asks ("xhigh", "a fondo", "exhaustivo") or the role sits in sol's row. Reserve `max` for a single hardest problem (one stuck bug, one judge on a critical design), never fleet-wide: 10 agents at `max` is the slowest possible run.
- Legacy `gpt-5.5` still works; use it only if the user names it.
- State in your plan paragraph which model+effort each phase uses.

## Hard limits

- **Max 10 Codex agents running concurrently.** Before spawning, count your running background tasks; if 10 are live, wait for notifications and backfill as slots free up.
- Max ~30 agents per full run unless the user asks for more. `log` what you're skipping if you bound coverage — no silent truncation.

## Run layout

```
/tmp/ultracodex/<run-slug>/
  plan.md                      # your decomposition, updated per phase
  <phase>/<agent-slug>/
    prompt.md                  # full self-contained prompt
    schema.json                # optional JSON Schema for structured output
    last-message.md            # agent's final answer (-o)
```

## Worker invocation

Always pass the prompt via stdin from `prompt.md` (prompts here are long):

```bash
codex exec -m gpt-5.6-terra -c model_reasoning_effort=medium \
  -C "<workdir>" -s read-only --skip-git-repo-check \
  -o "<agentdir>/last-message.md" \
  --output-schema "<agentdir>/schema.json" \
  - < "<agentdir>/prompt.md"
```

One background Bash call per agent (`run_in_background: true`). The harness notifies on exit — never poll or sleep. Sandbox: `read-only` for finders/verifiers/judges; `workspace-write` + a **dynamic worktree** per agent for implementers — use the auto-isolate/auto-clean pattern from the [[codex-agent]] skill (worktree created before spawn, removed automatically if the agent changed nothing, merged back by you if it did).

**On exit, before using a result:** check the exit code AND that `last-message.md` exists and is non-empty. On failure, read the captured stdout for the cause, respawn that one agent once (same prompt), and if it fails again drop it and say so in the synthesis — never silently count a dead agent as covered.

## Orchestration playbook

Run phases sequentially; fan out within each phase. Read every `last-message.md` before deciding the next phase — you are the synthesis layer, don't delegate it.

**1. Decompose (you, no agents).** Write `plan.md`: dimensions/sub-tasks, which phases apply, how many agents each gets within the cap, model+effort per phase. Show the user the plan in one short paragraph before spawning.

**2. Understand / Find — parallel fan-out.** One agent per dimension or lens (correctness, security, perf, architecture, by-subsystem, by-entrypoint...). Give each a *distinct* angle — diversity beats redundancy. Use `schema.json` so findings come back as structured JSON you can merge.

**OpenAI strict-schema rules (the API 400s if violated — verified twice in practice):**
- EVERY object (root and nested, including array `items`) must carry `"additionalProperties": false`.
- `required` must list EVERY key in `properties` — optional fields don't exist; model "may omit" is expressed with `"type": ["string","null"]`, not by leaving it out of `required`.
- Before spawning, sanity-check with: `python3 -c "import json,sys; ...iterate objects, assert additionalProperties is False and set(required)==set(properties)..."` or just eyeball both rules on every object.

```json
{"type":"object","additionalProperties":false,"properties":{"findings":{"type":"array","items":{"type":"object","additionalProperties":false,
 "properties":{"title":{"type":"string"},"file":{"type":"string"},"detail":{"type":"string"},
 "severity":{"type":"string","enum":["low","medium","high"]}},
 "required":["title","file","detail","severity"]}}},"required":["findings"]}
```

**3. Dedup (you, plain reasoning).** Merge findings across agents by file/claim before paying for verification.

**4. Adversarial verify.** For each surviving finding, spawn skeptic agents prompted to **refute** it ("Try to refute this claim. Default to refuted if you cannot reproduce/confirm it from the code."). Scale votes to stakes: 1 terra skeptic per finding normally; 3 with majority vote when the user asked for a thorough audit, using `sol` skeptics on high-severity findings. Kill anything refuted.

**5. Implement (only if the task asks for changes).** One agent per independent change, each in its own dynamic worktree, `workspace-write` — terra for straightforward changes, sol for gnarly ones. Prompt must include acceptance criteria and "end with a list of changed files". After each finishes: check `git diff --stat` in its worktree before trusting the report. Unchanged worktrees are removed automatically; changed ones you merge yourself, resolve conflicts, then remove.

**6. Verify / completeness critic.** One final agent (or one per implemented change) asking: does it build/test, and "what's missing — a dimension not swept, a claim unverified?" If it surfaces real gaps and budget remains, loop back one phase. Stop after 2 consecutive dry rounds.

**7. Synthesize (you).** Final message to the user: confirmed findings/changes with file:line references, what was refuted, what was skipped or died and why. Plain prose, no codenames from the run.

## Design-task variant

For "design X" / open-ended problems, replace phases 2–4 with a **judge panel**: 3–4 agents each producing an independent proposal from a different bias (MVP-first, risk-first, user-first, perf-first), then 2 `sol` judge agents scoring all proposals against the requirements. You synthesize from the winner, grafting the best ideas from runners-up.

## Scaling to the ask

- "revisa/encuentra bugs" → 3–4 terra finders, 1-vote verify (~6–8 agents).
- "audita a fondo / sé exhaustivo" → 6–8 finders, 3-vote adversarial verify with sol on high-severity, completeness loop (~20–30 agents).
- When unsure, ask nothing — scale to the wording and say what you chose in the plan paragraph.
