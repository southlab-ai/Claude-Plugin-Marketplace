---
name: council-consult
description: Adversarial consultation with configurable teammates. Supports default, debate, plan, and reflect modes.
---

# Council Consultation

You are the **team-lead** — orchestrator and synthesizer. Follow this protocol exactly.

## Input

Goal: "$ARGUMENTS"

ROLES (optional): If the goal text contains "ROLES:" followed by a comma-separated list of role names (e.g., "ROLES: architect, security-auditor, ux-designer"), extract those roles and remove the ROLES clause from the goal text. Otherwise, use the default roles.

If no goal provided, ask the user what they want to consult on and stop.

## Step 1: Verify

Check if `.council/` exists in the current project directory. If not, tell the user: "Run `/council:init` first." and stop.

## Step 2: Route Mode

Analyze the goal text and determine the consultation mode:

- **DEBATE MODE**: Goal contains debate/comparison language ("debate", "vs", "compare", "which is better", "argue for/against", "pros and cons", "trade-offs between")
- **PLAN MODE**: Goal asks for a plan/roadmap/PRD/spec ("plan", "roadmap", "PRD", "spec", "design", "architect", "implementation plan")
- **REFLECT MODE**: Goal is meta/reflective ("review our decisions", "what should we focus on", "gaps in our approach", "retrospective", "what have we missed")
- **DEFAULT MODE**: Everything else

If multiple modes match, pick the strongest match. State which mode you selected before continuing.

## Step 3: Load Memory

**REFLECT MODE**: Call both `council_memory_load` (with `goal`: "$ARGUMENTS", `max_tokens`: 4000) AND `council_memory_status` (with `project_dir`). Save both outputs — teammates will analyze decision history instead of the user's literal goal.

**All other modes**: Call `council_memory_load` with:
- `project_dir`: current project root (absolute path)
- `goal`: "$ARGUMENTS"
- `max_tokens`: 4000

Save the returned memory text — you'll inject it into teammate prompts.

## Step 4: Create Team

Use `TeamCreate` to create a team:
- `team_name`: "council"
- `description`: "Council consultation: <short version of goal>"

## Step 5: Spawn Teammates

### Determine roles

**If ROLES provided**: Parse the comma-separated list. Rules:
- Maximum 5 teammates. If more than 5 provided, truncate to 5 and warn the user.
- At least one adversarial role MUST be present. If no role name contains "critic" or "auditor", auto-add "critic" to the list.
- For each role: use `subagent_type: "the-council:critic"` if the role name contains "critic" or "auditor". Otherwise use `subagent_type: "the-council:strategist"`. If a matching agent template exists (e.g., `the-council:architect` for role "architect"), use that instead.
- Name each teammate by its role name.

**If ROLES not provided (default)**: Spawn the default 3 teammates:
- `strategist-alpha` (subagent_type: `the-council:strategist`)
- `strategist-beta` (subagent_type: `the-council:strategist`)
- `critic` (subagent_type: `the-council:critic`)

### Launch teammates

Use the **Task tool** to launch ALL teammates in **PARALLEL** (all in the same message). All MUST include `team_name: "council"` and a `name` parameter.

**Default roles prompt**:

**Strategist Alpha** — `name: "strategist-alpha"`:
```
GOAL: <the user's goal>

MEMORY LENS: As a strategist, weight entries about opportunities, implementation approaches, and architectural decisions most heavily.
MEMORY (from past consultations):
<strategist-relevant portion of memory from Step 3>

You are Strategist Alpha (ambitious, forward-thinking). Analyze this goal. 300-500 words.
Start with your recommendation. Push for the best possible outcome.
When done, send your full analysis to "team-lead" via SendMessage.
```

**Strategist Beta** — `name: "strategist-beta"`:
```
GOAL: <the user's goal>

MEMORY LENS: As a strategist, weight entries about risks of over-engineering, simpler alternatives, and past failures from complexity. Prefer cautious interpretations.
MEMORY (from past consultations):
<strategist-relevant portion of memory from Step 3>

You are Strategist Beta (pragmatic, conservative). Analyze this goal. 300-500 words.
Start with what's achievable and safe. Minimize risk and complexity.
When done, send your full analysis to "team-lead" via SendMessage.
```

**Critic** — `name: "critic"`:
```
GOAL: <the user's goal>

MEMORY LENS: As a critic, weight entries about risks, past failures, quality issues, and unresolved warnings most heavily. Pay special attention to entries marked [stale: Xd] — validate them before others cite them.
MEMORY (from past consultations):
<critic-relevant portion of memory from Step 3>

Critique this goal. 300-500 words. Start with the most critical issue. Every issue needs a fix.
When done, send your full analysis to "team-lead" via SendMessage.
```

**Custom roles prompt** (for each non-default role):
```
GOAL: <the user's goal>

MEMORY LENS: As a <role-name>, weight entries most relevant to your specialist domain. Interpret past decisions through your expertise.
MEMORY (from past consultations):
<relevant portion of memory from Step 3>

You are the <role-name>. Analyze this goal from your specialist perspective. 300-500 words.
Start with your most important finding or recommendation.
When done, send your full analysis to "team-lead" via SendMessage.
```

**REFLECT MODE override**: Instead of the user's literal goal, give each teammate this prompt:
```
MEMORY LENS: Review all entries for gaps, contradictions, and topics that need follow-up consultation.
DECISION HISTORY:
<full output from council_memory_load AND council_memory_status>

Review the decision history above. Identify gaps, risks, contradictions, or topics that should be consulted on next. 300-500 words.
When done, send your full analysis to "team-lead" via SendMessage.
```

Wait for all teammates to send their analyses back.

## Step 6: Synthesize

This step varies by mode.

### DEFAULT MODE

You received analyses from all teammates via SendMessage. Provide YOUR synthesis:
- Where teammates **agree** -> adopt immediately
- Where teammates **diverge** -> evaluate which approach better fits the context
- Where an adversarial role (critic/auditor) raises **valid concerns** -> incorporate fixes
- Where one raises something others missed -> incorporate
- Be explicit about what you adopted from each teammate

**One round only.** No re-consultation. No loops.

### DEBATE MODE

> Cost note: Debate mode uses ~2-3x tokens of default mode due to the rebuttal round.

**Step 6a — Forward positions**: Send each teammate's analysis to all other teammates via `SendMessage`. Include a label: "[Round 1] Position from <teammate-name>:".

**Step 6b — Collect rebuttals**: Each teammate reads the others' positions and sends a REVISED position (rebuttal) to team-lead. Instruct each via `SendMessage`:
```
[Round 2 — Rebuttal] Read the other positions forwarded to you. In 200-300 words, respond: where do you agree, where do you disagree, and what's your revised position? Send to "team-lead".
```

Wait for all rebuttal messages.

**Step 6c — Synthesize from rebuttals**: Synthesize from the REVISED positions (not the originals). Apply the same synthesis rules as DEFAULT MODE. Note where positions shifted between rounds.

**Hard cap: 1 rebuttal round only.** Do not run additional rounds.

### PLAN MODE

Apply the same synthesis rules as DEFAULT MODE, then format your synthesis as an actionable plan:
- Numbered steps with clear deliverables
- Dependencies between steps noted (e.g., "depends on step 2")
- Implementation order (all steps are mandatory — do not defer or deprioritize any requested feature)
- Each step should be specific enough for Claude to implement

### REFLECT MODE

Synthesize the analyses into a prioritized list of recommended consultations:
1. Topic / question to consult on
2. Why it matters (risk, gap, or opportunity)
3. Suggested priority (high/medium/low)

## Step 7: Record

Call `council_memory_record` with:
- `project_dir`: same as Step 3
- `goal`: the original goal
- `strategist_summary`: 1-2 sentence summary combining all non-adversarial teammates' positions (note where they agreed/diverged). For default roles, this combines both strategists. For custom roles, concatenate all non-critic/non-auditor summaries.
- `critic_summary`: 1-2 sentence summary combining all adversarial teammates' (critic/auditor) positions. For default roles, this is the critic's position. For custom roles, concatenate all critic/auditor summaries.
- `decision`: your team-lead decision and reasoning (1-3 sentences)
- `strategist_lesson`: (optional) reusable insight from the non-adversarial analysis
- `critic_lesson`: (optional) reusable insight from adversarial analysis
- `hub_lesson`: (optional) meta-lesson from the synthesis
- `importance`: 1-10 based on decision significance
- `pin`: true only for critical, project-wide decisions

## Step 8: Cleanup

Shut down all spawned teammates and delete the team:
1. For each teammate: `SendMessage` with `type: "shutdown_request"` to `"<teammate-name>"`
2. `TeamDelete` to remove the team

## Step 9: Present

Present your synthesis to the user. Include:
1. Mode selected and why
2. Roles used (note if custom or default)
3. Each teammate's key position
4. Your decision and reasoning
5. Any lessons recorded
