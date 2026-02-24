"""The Council MCP Server v3 — Memory-only persistence layer (6 tools)."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .memory import (
    build_memory_response,
    get_memory_health,
    get_original_prompt,
    load_index,
    record_consultation,
    save_active,
    save_index,
    store_original_prompt,
)

mcp = FastMCP("the-council")


def _council_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".council"


def _check_init(project_dir: str) -> str | None:
    council = _council_dir(project_dir)
    if not council.exists():
        return f"Council not initialized in {project_dir}. Run /council:init first."
    return None


# ---------------------------------------------------------------------------
# Tool 1: init
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_init(project_dir: str) -> str:
    """Create .council/ directory structure in a project."""
    council = _council_dir(project_dir)

    if council.exists():
        return f"Council already initialized at {council}. Use council_memory_reset(full=True) to reinitialize."

    # Create directories
    (council / "memory").mkdir(parents=True, exist_ok=True)

    # Initial Tier 0 index
    index = {
        "version": 1,
        "consultation_count": 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "compaction_watermark": "",
        "recent_decisions": [],
        "pinned": [],
        "topic_index": {},
        "original_prompt": "",
    }
    (council / "memory" / "index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )

    # Tier 2 archive files
    (council / "memory" / "decisions.md").write_text(
        "# Hub Decision Record\n", encoding="utf-8"
    )
    (council / "memory" / "lessons.jsonl").write_text("", encoding="utf-8")
    for role in ["strategist", "critic"]:
        (council / "memory" / f"{role}-log.md").write_text(
            f"# {role.title()} Memory Log\n", encoding="utf-8"
        )

    # .gitignore — exclude nothing by default (memory is persistent)
    gitignore = Path(project_dir) / ".gitignore"
    entry = "\n# Council memory (optional: uncomment to exclude)\n# .council/\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".council/" not in content:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write(entry)
    else:
        gitignore.write_text(entry, encoding="utf-8")

    return (
        f"Council initialized at {council}.\n"
        "Created: .council/memory/ (index.json, decisions.md, lessons.jsonl, role logs)\n"
        "Run /council:consult to start your first consultation."
    )


# ---------------------------------------------------------------------------
# Tool 2: load
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_load(
    project_dir: str, goal: str = "", max_tokens: int = 4000
) -> str:
    """Load optimized memory for teammate injection. Goal-filtered, budget-aware."""
    error = _check_init(project_dir)
    if error:
        return error

    return build_memory_response(project_dir, goal=goal, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Tool 3: record
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_record(
    project_dir: str,
    goal: str,
    strategist_summary: str,
    critic_summary: str,
    decision: str,
    strategist_lesson: str = "",
    critic_lesson: str = "",
    hub_lesson: str = "",
    importance: int = 5,
    pin: bool = False,
) -> str:
    """Record consultation results. Updates all memory tiers."""
    error = _check_init(project_dir)
    if error:
        return error

    # Generate session ID
    index = load_index(project_dir)
    count = index.get("consultation_count", 0) + 1
    session_id = f"S-{count:03d}"

    return record_consultation(
        project_dir=project_dir,
        session_id=session_id,
        goal=goal,
        strategist_summary=strategist_summary,
        critic_summary=critic_summary,
        decision=decision,
        strategist_lesson=strategist_lesson,
        critic_lesson=critic_lesson,
        hub_lesson=hub_lesson,
        importance=importance,
        pin=pin,
    )


# ---------------------------------------------------------------------------
# Tool 4: status
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_status(project_dir: str) -> str:
    """Council state: recent decisions, memory health, compaction recommendations."""
    error = _check_init(project_dir)
    if error:
        return error

    index = load_index(project_dir)
    health = get_memory_health(project_dir)
    parts = ["# Council Status\n"]

    # Summary
    parts.append(f"**Consultations:** {index.get('consultation_count', 0)}")
    parts.append(f"**Last updated:** {index.get('last_updated', 'never')}\n")

    # Recent decisions
    recent = index.get("recent_decisions", [])
    if recent:
        parts.append("## Recent Decisions\n")
        for d in recent:
            parts.append(f"- **{d.get('session_id', '?')}** ({d.get('date', '?')}): {d.get('goal_oneliner', '')} -> {d.get('decision_oneliner', '')}")
        parts.append("")

    # Pinned
    pinned = index.get("pinned", [])
    if pinned:
        parts.append("## Pinned\n")
        for p in pinned:
            parts.append(f"- [{p.get('source', '?')}] {p.get('text', '')}")
        parts.append("")

    # Memory health
    parts.append("## Memory Health\n")
    for role, info in health.get("roles", {}).items():
        status = "COMPACT RECOMMENDED" if info["needs_compaction"] else "OK"
        parts.append(
            f"- **{role}**: {info['active_entries']} entries, ~{info['active_tokens']} tokens, "
            f"log={info['log_lines']} lines — {status}"
        )

    if health.get("needs_compaction"):
        parts.append("\nRun `/council:maintain` to compact memory.")
    else:
        parts.append("\nMemory is healthy.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool 5: reset
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_reset(project_dir: str, full: bool = False) -> str:
    """Clear session data. full=True also clears all memory."""
    error = _check_init(project_dir)
    if error:
        return error

    council = _council_dir(project_dir)
    memory = council / "memory"

    if full:
        # Remove and recreate everything
        if memory.exists():
            shutil.rmtree(memory)
        memory.mkdir(parents=True, exist_ok=True)

        # Re-create initial files
        index = {
            "version": 1,
            "consultation_count": 0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "compaction_watermark": "",
            "recent_decisions": [],
            "pinned": [],
            "topic_index": {},
            "original_prompt": "",
        }
        (memory / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
        (memory / "decisions.md").write_text("# Hub Decision Record\n", encoding="utf-8")
        (memory / "lessons.jsonl").write_text("", encoding="utf-8")
        for role in ["strategist", "critic"]:
            (memory / f"{role}-log.md").write_text(f"# {role.title()} Memory Log\n", encoding="utf-8")

        return "Full reset complete. All memory cleared."

    # Soft reset: clear active memory entries but keep archives
    for role in ["strategist", "critic", "hub"]:
        active_path = memory / f"{role}-active.json"
        if active_path.exists():
            active_path.write_text(
                json.dumps({"version": 1, "role": role, "entries": []}, indent=2),
                encoding="utf-8",
            )

    # Reset index counters but keep topic_index
    index = load_index(project_dir)
    index["recent_decisions"] = []
    index["pinned"] = []
    save_index(project_dir, index)

    return "Session reset. Active memory cleared. Archives preserved."


# ---------------------------------------------------------------------------
# Tool 6: compact
# ---------------------------------------------------------------------------
@mcp.tool()
async def council_memory_compact(
    project_dir: str, role: str, compacted_entries: str
) -> str:
    """Write compacted active memory for a role. Called by curator."""
    error = _check_init(project_dir)
    if error:
        return error

    if role not in ("strategist", "critic", "hub"):
        return f"Invalid role: {role}. Must be strategist, critic, or hub."

    try:
        entries = json.loads(compacted_entries)
        if not isinstance(entries, list):
            return "compacted_entries must be a JSON array of entry objects."
    except json.JSONDecodeError as e:
        return f"Invalid JSON in compacted_entries: {e}"

    active = {"version": 1, "role": role, "entries": entries}
    save_active(project_dir, role, active)

    # Update compaction watermark in index
    index = load_index(project_dir)
    index["compaction_watermark"] = f"S-{index.get('consultation_count', 0):03d}"
    save_index(project_dir, index)

    return f"Compacted {role} active memory: {len(entries)} entries written."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
