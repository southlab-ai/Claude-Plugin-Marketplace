# Ultracodex

Ultracode-style multi-agent orchestration for Claude Code, using a fleet of **OpenAI Codex agents** (GPT-5.6 family — `sol` / `terra` / `luna`) as workers instead of Claude subagents.

Claude stays the orchestrator: it decomposes the task, writes self-contained prompts, spawns up to 10 concurrent `codex exec` background workers, adversarially verifies findings, and synthesizes the result. Codex-side tokens are billed to your own Codex plan.

## Skills

| Skill | Use for |
|-------|---------|
| `ultracodex` | Fleet orchestration: deep audits, broad reviews, migrations, multi-angle research or design. Trigger by saying "ultracodex" or asking to attack a task exhaustively with parallel Codex/GPT agents. |
| `codex-agent` | A single background Codex worker: delegate a task to Codex, run tasks in parallel, or get a second opinion from GPT. |

## What a run looks like

1. **Decompose** — Claude writes a plan with dimensions, agent counts, and model+effort per phase.
2. **Fan-out** — parallel finders, each with a distinct lens, returning structured JSON (strict OpenAI schemas).
3. **Dedup + adversarial verify** — skeptic agents try to *refute* every finding; refuted claims die.
4. **Implement** (if asked) — one agent per independent change, each in its own auto-cleaned git worktree.
5. **Completeness check + synthesis** — Claude reports confirmed findings/changes with file:line references.

For open-ended design tasks, phases 2–4 become a judge panel: 3–4 independent proposals from different biases, scored by `sol` judges.

## Requirements

- [OpenAI Codex CLI](https://developers.openai.com/codex/cli) installed and authenticated (`codex login`) with a plan that has GPT-5.6 access
- Claude Code (any recent version; no MCP server, skills only)

## Install

```
/plugin install ultracodex@southlab-marketplace
```

No setup command — invoke the `ultracodex` or `codex-agent` skill directly.

## License

MIT
