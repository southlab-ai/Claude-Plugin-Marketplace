---
name: codex-agent
description: Spawn OpenAI Codex CLI agents (GPT-5.6 family — sol/terra/luna) as native background workers via `codex exec`. Use when the user asks to delegate work to Codex, spawn codex/GPT agents, run tasks in parallel with Codex, or get a second opinion from GPT. Supports single or parallel agents, session resume, structured output, and web search.
---

# Codex Agent Spawner

Spawn non-interactive Codex CLI agents using `codex exec`. Requires the OpenAI Codex CLI installed and authenticated (`codex login`; auth stored in `~/.codex/auth.json`). **Always pin model and reasoning effort explicitly** — don't rely on `~/.codex/config.toml` defaults (they drift).

**Model: `gpt-5.6-sol` by default** for a single agent (flagship — a lone second opinion should be the strong one). Use `gpt-5.6-terra` for routine well-scoped subtasks, `gpt-5.6-luna` for mechanical extraction/classification. Legacy `gpt-5.5` only if the user names it. For fleets, the [[ultracodex]] skill has its own per-role table.

**Reasoning effort: `medium` by default.** Raise to `high`/`xhigh` only when the user asks (e.g. "xhigh", "a fondo", "máximo esfuerzo") or the subtask is genuinely hard (subtle debugging, architecture, security analysis); `max` (new in 5.6) for a single hardest problem. Valid values on 5.6: `low | medium | high | xhigh | max` (`minimal` is gone).

## Base command

```bash
codex exec \
  -m gpt-5.6-sol \
  -c model_reasoning_effort=medium \
  -C "<workdir>" \
  -s workspace-write \
  -o "<rundir>/last-message.md" \
  "<PROMPT>"
```

Run it with the Bash tool and `run_in_background: true`. The harness notifies you when it exits — do NOT poll or sleep. For long prompts, pipe via stdin (`codex exec ... -` with a heredoc) instead of an argv string.

## Per-run output directory

Before spawning, create a run dir and capture everything there:

```bash
RUNDIR="/tmp/codex-agents/<slug>"   # slug: short task name, add -2, -3 if it exists
mkdir -p "$RUNDIR"
```

- `-o "$RUNDIR/last-message.md"` — final answer (this is what you report back to the user).
- Append `--json > "$RUNDIR/events.jsonl"` only if the user wants a full trace; otherwise plain stdout (captured by the background task) is enough to monitor progress.
- The session id appears in the output header (`session id: <uuid>`) — note it so the agent can be resumed.

## Flag decisions

| Situation | Flags |
|---|---|
| Analysis / review / second opinion (no edits) | `-s read-only` |
| Implementation in a project | `-s workspace-write` |
| Working dir is not a git repo | add `--skip-git-repo-check` |
| Needs internet research | add `--search` |
| Throwaway question, no need to resume | add `--ephemeral` |
| Structured result you'll parse | `--output-schema <schema.json>` (write the JSON Schema file first) |
| Extra writable dirs | `--add-dir <dir>` (repeatable) |

Never use `--dangerously-bypass-approvals-and-sandbox` unless the user explicitly asks for it. Approval policy must be `never` for non-interactive runs — add `-c approval_policy=never` if the user's config doesn't already set it.

## Parallel agents

Spawn one background Bash call per agent, each with its own `$RUNDIR`. They run concurrently and each notifies on exit. Read-only agents can all share the same dir, no isolation needed.

## Dynamic worktree (auto-isolate, auto-clean)

Any agent that **writes inside a git repo** gets its own worktree — created before spawn, removed automatically if the agent changed nothing (mirrors the native `isolation: worktree` of the Agent tool):

```bash
# before spawn
WT="/tmp/codex-wt/<slug>"
git -C "<repo>" worktree add "$WT" -b "codex/<slug>"
# spawn the agent with: -C "$WT" -s workspace-write

# when the agent exits
if [ -z "$(git -C "$WT" status --porcelain)" ] && [ -z "$(git -C "$WT" log "$(git -C "<repo>" rev-parse --abbrev-ref HEAD)..codex/<slug>" --oneline 2>/dev/null)" ]; then
  # unchanged → clean up silently
  git -C "<repo>" worktree remove "$WT" && git -C "<repo>" branch -d "codex/<slug>"
else
  # changed → show the user `git -C "$WT" diff --stat`, apply/merge back, THEN remove worktree + branch
  :
fi
```

Skip the worktree only when there's a single writing agent and the user asked it to work directly on their tree.

## Prompt quality

Codex agents start cold — no conversation context. Each prompt must be self-contained:
- State the goal, the working directory layout if non-obvious, and acceptance criteria.
- Tell it what NOT to touch.
- Ask it to end with a summary of changed files (so `last-message.md` is useful).

## Resume / follow-up

```bash
codex exec resume <session-id> -m gpt-5.6-sol -c model_reasoning_effort=medium "<follow-up>"
codex exec resume --last ...   # most recent session
```

## Reporting back

When an agent finishes: read `$RUNDIR/last-message.md` and relay the result. If the exit code is non-zero, read the captured stdout/stderr from the background task and report the failure honestly. Don't claim work is done without checking the final message and (for code changes) `git -C <workdir> diff --stat`.
