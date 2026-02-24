"""Three-tier, budget-aware, goal-filtered memory engine for The Council."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Topic extraction (zero-dependency, keyword-based)
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "database": ["database", "sql", "query", "schema", "migration", "postgres", "mysql", "sqlite", "orm", "table", "index", "pgbouncer", "pool"],
    "authentication": ["auth", "login", "token", "jwt", "oauth", "session", "password", "credential", "sso", "saml"],
    "api": ["api", "endpoint", "rest", "graphql", "grpc", "route", "request", "response", "middleware", "cors", "rate-limit"],
    "frontend": ["react", "vue", "angular", "component", "css", "dom", "ui", "ux", "layout", "responsive", "tailwind"],
    "performance": ["performance", "cache", "latency", "throughput", "optimize", "bottleneck", "profil", "benchmark", "pool", "batch"],
    "security": ["security", "vulnerability", "xss", "injection", "encrypt", "hash", "cert", "tls", "ssl", "firewall", "audit"],
    "testing": ["test", "spec", "assert", "mock", "fixture", "coverage", "ci", "integration", "unit", "e2e"],
    "infrastructure": ["deploy", "docker", "kubernetes", "k8s", "terraform", "aws", "cloud", "container", "pipeline", "cd", "ci"],
    "architecture": ["architecture", "pattern", "monolith", "microservice", "monorepo", "module", "layer", "decouple", "interface", "abstract"],
    "data": ["data", "etl", "pipeline", "stream", "kafka", "queue", "event", "message", "pubsub", "webhook"],
}

_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
    "been", "have", "has", "had", "not", "but", "what", "all", "can", "will",
    "one", "its", "also", "into", "than", "each", "use", "should", "would",
    "could", "may", "need", "how", "when", "where", "which", "just", "more",
    "about", "they", "them", "then", "there", "here", "only", "some", "very",
})

SYNONYM_MAP: dict[str, str] = {
    "k8s": "kubernetes", "kube": "kubernetes", "eks": "kubernetes",
    "gke": "kubernetes", "aks": "kubernetes", "helm": "kubernetes",
    "ec2": "aws", "s3": "aws", "lambda": "aws", "rds": "aws",
    "gcp": "cloud", "azure": "cloud",
    "ci-cd": "pipeline", "github-actions": "pipeline", "jenkins": "pipeline",
    "gitlab-ci": "pipeline", "circleci": "pipeline",
    "nginx": "deploy", "caddy": "deploy", "traefik": "deploy",
    "mongo": "database", "mongodb": "database", "dynamo": "database",
    "dynamodb": "database", "pg": "database", "postgres": "database",
    "redis": "cache", "memcached": "cache",
    "autoscaling": "performance", "scale-out": "performance",
    "horizontal-scaling": "performance", "elastic-scaling": "performance",
    "okta": "sso", "auth0": "oauth", "cognito": "oauth", "keycloak": "sso",
    "passkey": "credential", "webauthn": "credential",
    "mfa": "authentication", "2fa": "authentication", "totp": "authentication",
    "nextjs": "react", "remix": "react", "gatsby": "react",
    "nuxt": "vue", "svelte": "component",
    "shadcn": "tailwind", "mui": "component", "chakra": "component",
    "jest": "test", "vitest": "test", "pytest": "test",
    "cypress": "e2e", "playwright": "e2e", "selenium": "e2e",
    "cqrs": "pattern", "ddd": "architecture", "hexagonal": "architecture",
    "rabbitmq": "queue", "sqs": "queue", "nats": "message",
    "pulsar": "stream", "spark": "etl",
}


def extract_topics(text: str, topic_index: dict | None = None) -> set[str]:
    """Extract topic tags from text. Checks dynamic keywords from topic_index first,
    falls back to TOPIC_KEYWORDS seed."""
    raw_words = set(re.findall(r"[a-z0-9-]+", text.lower()))

    # Expand synonyms
    expanded_synonyms: set[str] = {SYNONYM_MAP[w] for w in raw_words if w in SYNONYM_MAP}

    # Bigrams from original word sequence (preserves text order)
    word_seq = re.findall(r"[a-z0-9]+", text.lower())
    bigrams: set[str] = {f"{word_seq[i]}-{word_seq[i+1]}" for i in range(len(word_seq) - 1)}

    words = raw_words | expanded_synonyms | bigrams
    topics = set()

    # Merge dynamic keywords from topic_index with seed keywords
    keyword_map: dict[str, list[str]] = {t: list(kws) for t, kws in TOPIC_KEYWORDS.items()}
    if topic_index:
        for topic, info in topic_index.items():
            dynamic_kws = info.get("keywords", [])
            if topic in keyword_map:
                keyword_map[topic] = list(set(keyword_map[topic] + dynamic_kws))
            else:
                keyword_map[topic] = dynamic_kws

    for topic, keywords in keyword_map.items():
        if keywords and any(kw in words or any(kw in w for w in words) for kw in keywords):
            topics.add(topic)
    return topics


# ---------------------------------------------------------------------------
# Relevance scoring (goal-aware retrieval)
# ---------------------------------------------------------------------------
def compute_relevance(entry: dict, goal: str, topic_index: dict | None = None) -> float:
    """Score how relevant a memory entry is to the current goal."""
    entry_topics = set(entry.get("topics", []))
    goal_topics = extract_topics(goal, topic_index)

    # Topic overlap
    if entry_topics:
        topic_score = len(entry_topics & goal_topics) / max(len(entry_topics), 1)
    else:
        topic_score = 0.0

    # Keyword overlap (split direct vs synonym scoring)
    goal_words_raw = set(re.findall(r"[a-z0-9-]+", goal.lower()))
    goal_words_expanded = {SYNONYM_MAP[w] for w in goal_words_raw if w in SYNONYM_MAP}
    entry_text = entry.get("text", "") + " " + entry.get("headline", "")
    entry_words = set(re.findall(r"[a-z0-9-]+", entry_text.lower()))
    direct_overlap = len(goal_words_raw & entry_words) / max(len(goal_words_raw), 1)
    synonym_overlap = (
        len(goal_words_expanded & entry_words) / max(len(goal_words_expanded), 1)
        if goal_words_expanded else 0.0
    )
    keyword_overlap = direct_overlap + synonym_overlap * 0.5

    # Recency factor
    try:
        created = datetime.fromisoformat(entry.get("created", ""))
        days_old = (datetime.now(timezone.utc) - created).days
    except (ValueError, TypeError):
        days_old = 0
    recency = max(0.0, 0.3 - (days_old * 0.01))

    base_score = topic_score * 0.5 + keyword_overlap * 0.3 + recency * 0.2

    # Staleness penalty — pinned entries are ALWAYS exempt
    if entry.get("pinned"):
        return base_score

    last_validated_str = entry.get("last_validated") or entry.get("created", "")
    try:
        val_dt = datetime.fromisoformat(last_validated_str)
        stale_days = (datetime.now(timezone.utc) - val_dt).days
    except (ValueError, TypeError):
        stale_days = 0  # default: non-stale on parse failure

    staleness_factor = 0.7 if stale_days > 90 else 1.0
    return base_score * staleness_factor


# ---------------------------------------------------------------------------
# Stale marker for output formatting
# ---------------------------------------------------------------------------
def _stale_marker(entry: dict) -> str:
    if entry.get("pinned"):
        return ""
    last_val = entry.get("last_validated") or entry.get("created", "")
    try:
        val_dt = datetime.fromisoformat(last_val)
        days = (datetime.now(timezone.utc) - val_dt).days
        return f" [stale: {days}d]" if days > 90 else ""
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Token estimation (simple word-based heuristic)
# ---------------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Rough token count: ~0.75 words per token for English."""
    return max(1, int(len(text.split()) * 1.33))


# ---------------------------------------------------------------------------
# Memory file I/O
# ---------------------------------------------------------------------------
def _memory_dir(project_dir: str) -> Path:
    return Path(project_dir) / ".council" / "memory"


def load_index(project_dir: str) -> dict:
    """Load Tier 0 index. Returns empty structure if missing."""
    index_path = _memory_dir(project_dir) / "index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            # Auto-migrate v1 -> v2
            if data.get("version", 1) < 2:
                data["version"] = 2
                index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 2,
        "consultation_count": 0,
        "last_updated": "",
        "compaction_watermark": "",
        "recent_decisions": [],
        "pinned": [],
        "topic_index": {},
        "original_prompt": "",
    }


def save_index(project_dir: str, index: dict) -> None:
    """Write Tier 0 index."""
    index_path = _memory_dir(project_dir) / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def load_active(project_dir: str, role: str) -> dict:
    """Load Tier 1 active memory for a role."""
    active_path = _memory_dir(project_dir) / f"{role}-active.json"
    if active_path.exists():
        try:
            data = json.loads(active_path.read_text(encoding="utf-8"))
            # Auto-migrate v1 -> v2
            if data.get("version", 1) < 2:
                data["version"] = 2
                active_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 2, "role": role, "entries": []}


def save_active(project_dir: str, role: str, data: dict) -> None:
    """Write Tier 1 active memory for a role."""
    active_path = _memory_dir(project_dir) / f"{role}-active.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Original prompt storage (for feature-tracking in build pipeline)
# ---------------------------------------------------------------------------
def store_original_prompt(project_dir: str, prompt: str) -> None:
    """Store the original user prompt for feature-tracking throughout the pipeline."""
    index = load_index(project_dir)
    index["original_prompt"] = prompt
    save_index(project_dir, index)


def get_original_prompt(project_dir: str) -> str:
    """Retrieve the stored original user prompt."""
    index = load_index(project_dir)
    return index.get("original_prompt", "")


# ---------------------------------------------------------------------------
# Budget-aware memory retrieval
# ---------------------------------------------------------------------------
def build_memory_response(
    project_dir: str,
    goal: str = "",
    max_tokens: int = 4000,
    role_filter: str = "",
) -> str:
    """Build budget-aware memory response. Never exceeds max_tokens.

    Packing order:
    1. Always: Tier 0 index (~200-500 tokens)
    2. Goal-relevant Tier 1 entries, sorted by relevance*0.6 + importance*0.4
    3. If budget remains: top non-relevant entries by importance alone
    4. If budget tight (< 1000 after index): index + top 3 as 1-line summaries
    """
    index = load_index(project_dir)
    topic_idx = index.get("topic_index", {})

    # --- Tier 0: Index section (always included) ---
    tier0_parts = []
    tier0_parts.append(f"## Your Memory ({index.get('consultation_count', 0)} consultations, budget: {max_tokens} tokens)\n")

    # Pinned items
    pinned = index.get("pinned", [])
    if pinned:
        tier0_parts.append("### Critical (always remember)")
        for p in pinned:
            tier0_parts.append(f"- [pinned] {p.get('text', '')}")
        tier0_parts.append("")

    # Recent decisions
    recent = index.get("recent_decisions", [])[-3:]
    if recent:
        tier0_parts.append("### Recent decisions")
        for d in recent:
            tier0_parts.append(f"- {d.get('session_id', '?')}: {d.get('goal_oneliner', '')} -> {d.get('decision_oneliner', '')}")
        tier0_parts.append("")

    # Archive signpost (~150-200 tokens, always included)
    memory_path = _memory_dir(project_dir)
    decisions_path = memory_path / "decisions.md"
    lessons_path = memory_path / "lessons.jsonl"
    decision_count = 0
    lesson_count = 0
    if decisions_path.exists():
        decision_count = decisions_path.read_text(encoding="utf-8").count("\n## ")
    if lessons_path.exists():
        content = lessons_path.read_text(encoding="utf-8").strip()
        lesson_count = sum(1 for line in content.split("\n") if line.strip()) if content else 0
    if decision_count or lesson_count:
        tier0_parts.append("### Archive")
        tier0_parts.append(f"- {decision_count} decisions, {lesson_count} lessons archived")
        if topic_idx:
            densities = []
            for topic, info in sorted(
                topic_idx.items(),
                key=lambda x: len(x[1].get("decision_ids", [])),
                reverse=True,
            )[:5]:
                count = len(info.get("decision_ids", []))
                if count > 0:
                    recent_decisions = info.get("decisions", [])
                    if recent_decisions:
                        latest = recent_decisions[-1].get("summary", "")[:60]
                        densities.append(f"{topic}: {count} (latest: {latest})")
                    else:
                        densities.append(f"{topic}: {count}")
            if densities:
                tier0_parts.append(f"- Topics: {', '.join(densities)}")
        tier0_parts.append("")

    tier0_text = "\n".join(tier0_parts)
    tier0_tokens = estimate_tokens(tier0_text)
    remaining = max_tokens - tier0_tokens

    # --- Budget tight? Minimal response ---
    if remaining < 1000:
        roles = [role_filter] if role_filter else ["strategist", "critic", "hub"]
        summaries = []
        for role in roles:
            active = load_active(project_dir, role)
            entries = active.get("entries", [])
            top3 = sorted(entries, key=lambda e: e.get("importance", 0), reverse=True)[:3]
            for e in top3:
                summaries.append(f"- {e.get('id', '?')} [imp:{e.get('importance', 0)}]{_stale_marker(e)}: {e.get('headline', e.get('text', '')[:80])}")
        if summaries:
            return tier0_text + "### Key memories (budget-limited)\n" + "\n".join(summaries)
        return tier0_text.strip()

    # --- Tier 1: Active memory entries ---
    roles = [role_filter] if role_filter else ["strategist", "critic", "hub"]
    all_entries: list[tuple[float, dict]] = []

    for role in roles:
        active = load_active(project_dir, role)
        for entry in active.get("entries", []):
            if goal:
                relevance = compute_relevance(entry, goal, topic_idx)
            else:
                relevance = 0.0
            importance = entry.get("importance", 5) / 10.0
            score = relevance * 0.6 + importance * 0.4
            all_entries.append((score, entry))

    # Sort by combined score descending
    all_entries.sort(key=lambda x: x[0], reverse=True)

    # Pack entries within budget — 3-tier strategy
    used_tokens = 0
    relevance_threshold = 0.2

    if remaining >= 2500:
        # --- Generous budget: full text when possible ---
        relevant_parts = []
        other_parts = []
        for score, entry in all_entries:
            if remaining - used_tokens > 2000:
                text = entry.get("text", "")
            else:
                text = entry.get("headline", entry.get("text", "")[:80])

            line = f"- {entry.get('id', '?')} [imp:{entry.get('importance', 0)}]{_stale_marker(entry)}: {text}"
            line_tokens = estimate_tokens(line)

            if used_tokens + line_tokens > remaining:
                break

            if score >= relevance_threshold and goal:
                relevant_parts.append(line)
            else:
                other_parts.append(line)
            used_tokens += line_tokens

        sections = [tier0_text]
        if relevant_parts:
            sections.append("### Relevant to this goal")
            sections.extend(relevant_parts)
            sections.append("")
        if other_parts:
            sections.append("### Other important context")
            sections.extend(other_parts)
            sections.append("")

    elif remaining >= 800:
        # --- Normal budget: two-pass (oneliners, then upgrade top entries) ---
        # Pass 1: emit all entries as one-liners, track metadata
        packed: list[tuple[float, dict, str, int]] = []  # (score, entry, oneliner, oneliner_tokens)
        for score, entry in all_entries:
            headline = entry.get("headline", entry.get("text", "")[:80])
            oneliner = f"- {entry.get('id', '?')} [imp:{entry.get('importance', 0)}]{_stale_marker(entry)}: {headline}"
            oneliner_tokens = estimate_tokens(oneliner)
            if used_tokens + oneliner_tokens > remaining:
                break
            packed.append((score, entry, oneliner, oneliner_tokens))
            used_tokens += oneliner_tokens

        # Pass 2: upgrade highest-scored entries to full text if budget allows
        output_lines = [p[2] for p in packed]  # start with all oneliners
        packed_by_score = sorted(enumerate(packed), key=lambda x: x[1][0], reverse=True)
        for idx, (score, entry, oneliner, oneliner_tokens) in packed_by_score:
            full_text = entry.get("text", "")
            full_line = f"- {entry.get('id', '?')} [imp:{entry.get('importance', 0)}]{_stale_marker(entry)}: {full_text}"
            full_tokens = estimate_tokens(full_line)
            extra_tokens = full_tokens - oneliner_tokens
            if extra_tokens > 0 and used_tokens + extra_tokens <= remaining:
                output_lines[idx] = full_line
                used_tokens += extra_tokens

        sections = [tier0_text]
        sections.append("### Memory Overview")
        sections.extend(output_lines)
        sections.append("")

    else:
        # --- Tight budget (remaining < 800): oneliners only ---
        relevant_parts = []
        other_parts = []
        for score, entry in all_entries:
            text = entry.get("headline", entry.get("text", "")[:80])
            line = f"- {entry.get('id', '?')} [imp:{entry.get('importance', 0)}]{_stale_marker(entry)}: {text}"
            line_tokens = estimate_tokens(line)

            if used_tokens + line_tokens > remaining:
                break

            if score >= relevance_threshold and goal:
                relevant_parts.append(line)
            else:
                other_parts.append(line)
            used_tokens += line_tokens

        sections = [tier0_text]
        if relevant_parts:
            sections.append("### Relevant to this goal")
            sections.extend(relevant_parts)
            sections.append("")
        if other_parts:
            sections.append("### Other important context")
            sections.extend(other_parts)
            sections.append("")

    # --- Archive excerpts (from lessons.jsonl, pre-filtered by topic) ---
    def _score_lesson(lesson: dict, goal: str) -> float:
        """Lightweight relevance score for archive lessons."""
        lesson_words = set(re.findall(r"[a-z0-9-]+", lesson.get("lesson", "").lower()))
        goal_words = set(re.findall(r"[a-z0-9-]+", goal.lower())) - _STOPWORDS
        return len(goal_words & lesson_words) / max(len(goal_words), 1) if goal_words else 0.0

    if goal and remaining - used_tokens > 200:
        goal_topics_set = extract_topics(goal, topic_idx)
        relevant_sessions = set()
        for t in goal_topics_set:
            if t in topic_idx:
                relevant_sessions.update(topic_idx[t].get("decision_ids", []))

        if relevant_sessions:
            archive_lessons = []
            if lessons_path.exists():
                for line in lessons_path.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        lesson = json.loads(line)
                        if lesson.get("session") in relevant_sessions:
                            archive_lessons.append(lesson)
                    except json.JSONDecodeError:
                        continue

            # A7: Cap at 200 most recent before scoring
            archive_lessons = archive_lessons[-200:]

            if archive_lessons:
                # A8: Relevance-scored selection (top 12)
                scored_lessons = sorted(archive_lessons, key=lambda l: _score_lesson(l, goal), reverse=True)

                # A9: Archive token cap
                archive_token_cap = min(int((remaining - used_tokens) * 0.3), 600)
                archive_used = 0

                excerpt_parts = ["### Archived Lessons (from past consultations)"]
                for lesson in scored_lessons[:12]:
                    text = lesson.get("lesson", "")[:120]
                    source = lesson.get("source", "?")
                    session = lesson.get("session", "?")
                    entry_line = f"- [{source}/{session}] {text}"
                    line_tokens = estimate_tokens(entry_line)
                    if archive_used + line_tokens > archive_token_cap:
                        break
                    excerpt_parts.append(entry_line)
                    archive_used += line_tokens

                used_tokens += archive_used

                if len(excerpt_parts) > 1:
                    sections.append("\n".join(excerpt_parts))
                    sections.append("")

    return "\n".join(sections).strip()


# ---------------------------------------------------------------------------
# Recording: update all three tiers
# ---------------------------------------------------------------------------
def _next_id(role: str, active: dict) -> str:
    """Generate next memory entry ID."""
    entries = active.get("entries", [])
    max_num = 0
    for e in entries:
        eid = e.get("id", "")
        parts = eid.rsplit("-", 1)
        if len(parts) == 2:
            try:
                max_num = max(max_num, int(parts[1]))
            except ValueError:
                pass
    return f"M-{role}-{max_num + 1:03d}"


def record_consultation(
    project_dir: str,
    session_id: str,
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
    """Record consultation results across all three memory tiers.

    Tier 0: Update index (consultation count, recent decisions, topic index)
    Tier 1: Add entries to active memory files
    Tier 2: Append to archive logs
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    memory = _memory_dir(project_dir)
    memory.mkdir(parents=True, exist_ok=True)

    goal_topics = list(extract_topics(goal))

    # --- Tier 2: Append to archive (never modified, always grows) ---
    # decisions.md
    decisions_path = memory / "decisions.md"
    with open(decisions_path, "a", encoding="utf-8") as f:
        if decisions_path.stat().st_size == 0:
            f.write("# Hub Decision Record\n")
        f.write(f"\n## {date_str} — {goal[:80]} (session {session_id})\n\n")
        f.write(f"- **Goal:** {goal}\n")
        f.write(f"- **Strategist:** {strategist_summary}\n")
        f.write(f"- **Critic:** {critic_summary}\n")
        f.write(f"- **Decision:** {decision}\n\n")

    # lessons.jsonl
    lessons_path = memory / "lessons.jsonl"
    with open(lessons_path, "a", encoding="utf-8") as f:
        for source, lesson in [("strategist", strategist_lesson), ("critic", critic_lesson), ("hub", hub_lesson)]:
            if lesson:
                f.write(json.dumps({"ts": now_iso, "lesson": lesson, "source": source, "session": session_id}) + "\n")

    # Role logs
    for role, lesson in [("strategist", strategist_lesson), ("critic", critic_lesson)]:
        if lesson:
            log_path = memory / f"{role}-log.md"
            with open(log_path, "a", encoding="utf-8") as f:
                if log_path.stat().st_size == 0:
                    f.write(f"# {role.title()} Memory Log\n")
                f.write(f"\n### Session {session_id} ({date_str})\n\n{lesson}\n")

    # --- Tier 1: Add to active memory ---
    for role, lesson in [("strategist", strategist_lesson), ("critic", critic_lesson), ("hub", hub_lesson)]:
        if lesson:
            active = load_active(project_dir, role)
            entry_id = _next_id(role, active)
            entry_topics = list(extract_topics(lesson))
            entry = {
                "id": entry_id,
                "topics": entry_topics or goal_topics,
                "detail_level": 3,
                "text": lesson,
                "headline": lesson[:100].split(".")[0] + "." if "." in lesson[:100] else lesson[:80],
                "importance": importance,
                "pinned": pin,
                "created": now_iso,
                "last_validated": now_iso,
                "last_referenced": now_iso,
                "referenced_count": 0,
                "source_sessions": [session_id],
                "supersedes": [],
            }
            active.setdefault("entries", []).append(entry)
            save_active(project_dir, role, active)

    # --- Tier 0: Update index ---
    index = load_index(project_dir)
    index["consultation_count"] = index.get("consultation_count", 0) + 1
    index["last_updated"] = now_iso

    # Recent decisions (keep last 5)
    decision_entry = {
        "session_id": session_id,
        "date": date_str,
        "goal_oneliner": goal[:100],
        "decision_oneliner": decision[:100],
        "importance": importance,
        "topics": goal_topics,
    }
    recent = index.get("recent_decisions", [])
    recent.append(decision_entry)
    index["recent_decisions"] = recent[-5:]

    # Pinned
    if pin:
        pin_entry = {
            "id": f"P-{session_id}",
            "text": decision[:150],
            "importance": importance,
            "source": "hub",
        }
        index.setdefault("pinned", []).append(pin_entry)

    # Topic index — grow keywords and track decisions
    ti = index.get("topic_index", {})
    candidate_words = set(re.findall(r"[a-z0-9-]+", (goal + " " + decision).lower()))
    candidate_words -= _STOPWORDS
    candidate_words = {w for w in candidate_words if len(w) >= 4}
    for topic in goal_topics:
        entry = ti.setdefault(topic, {"decision_ids": [], "memory_ids": [], "keywords": [], "decisions": []})
        entry.setdefault("keywords", [])
        entry.setdefault("decisions", [])
        if session_id not in entry["decision_ids"]:
            entry["decision_ids"].append(session_id)

        # Grow keywords (cap at 30 per topic)
        existing = set(entry["keywords"])
        entry["keywords"] = list(existing | candidate_words)[:30]

        # Track decisions (cap at 3 most recent)
        entry["decisions"].append({"session": session_id, "summary": decision[:100]})
        entry["decisions"] = entry["decisions"][-3:]
    index["topic_index"] = ti

    save_index(project_dir, index)

    return f"Recorded consultation {session_id}. Memory updated across all tiers."


# ---------------------------------------------------------------------------
# Memory health / compaction status
# ---------------------------------------------------------------------------
def get_memory_health(project_dir: str) -> dict:
    """Get memory health stats for compaction decisions."""
    memory = _memory_dir(project_dir)
    index = load_index(project_dir)

    health = {
        "consultation_count": index.get("consultation_count", 0),
        "last_updated": index.get("last_updated", ""),
        "compaction_watermark": index.get("compaction_watermark", ""),
        "roles": {},
        "needs_compaction": False,
    }

    for role in ["strategist", "critic", "hub"]:
        active = load_active(project_dir, role)
        entries = active.get("entries", [])
        entry_count = len(entries)
        total_tokens = sum(estimate_tokens(e.get("text", "")) for e in entries)

        log_path = memory / f"{role}-log.md"
        log_lines = 0
        if log_path.exists():
            log_lines = len(log_path.read_text(encoding="utf-8").strip().split("\n"))

        needs = total_tokens > 6000 or entry_count > 20
        if needs:
            health["needs_compaction"] = True

        health["roles"][role] = {
            "active_entries": entry_count,
            "active_tokens": total_tokens,
            "log_lines": log_lines,
            "needs_compaction": needs,
        }

    return health
