"""Shared fixtures for council memory tests."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


def _iso(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


@pytest.fixture
def tmp_project(tmp_path):
    """Creates a temp project with .council/memory/ structure."""
    memory_dir = tmp_path / ".council" / "memory"
    memory_dir.mkdir(parents=True)

    index = {
        "version": 1,
        "consultation_count": 0,
        "last_updated": "",
        "compaction_watermark": "",
        "recent_decisions": [],
        "pinned": [],
        "topic_index": {},
        "original_prompt": "",
    }
    (memory_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

    return str(tmp_path)


@pytest.fixture
def tmp_project_with_entries(tmp_project):
    """Project with seeded active memory entries."""
    memory_dir = Path(tmp_project) / ".council" / "memory"

    entries_fresh = [
        {
            "id": "M-strategist-001",
            "topics": ["infrastructure"],
            "text": "Deploy using Docker containers on Kubernetes for scalability.",
            "headline": "Deploy using Docker containers on Kubernetes.",
            "importance": 8,
            "pinned": False,
            "created": _iso(5),
            "last_validated": _iso(5),
            "last_referenced": _iso(5),
            "referenced_count": 1,
            "source_sessions": ["S-001"],
            "supersedes": [],
        },
        {
            "id": "M-strategist-002",
            "topics": ["database"],
            "text": "Use PostgreSQL for the primary data store.",
            "headline": "Use PostgreSQL for the primary data store.",
            "importance": 7,
            "pinned": False,
            "created": _iso(10),
            "last_validated": _iso(10),
            "last_referenced": _iso(10),
            "referenced_count": 0,
            "source_sessions": ["S-002"],
            "supersedes": [],
        },
    ]

    entries_stale = [
        {
            "id": "M-strategist-003",
            "topics": ["performance"],
            "text": "Cache API responses in Redis with 5-minute TTL.",
            "headline": "Cache API responses in Redis.",
            "importance": 6,
            "pinned": False,
            "created": _iso(120),
            "last_validated": _iso(120),
            "last_referenced": _iso(120),
            "referenced_count": 0,
            "source_sessions": ["S-003"],
            "supersedes": [],
        },
    ]

    entries_pinned_stale = [
        {
            "id": "M-hub-001",
            "topics": ["architecture"],
            "text": "This project uses hexagonal architecture. Do not change.",
            "headline": "This project uses hexagonal architecture.",
            "importance": 10,
            "pinned": True,
            "created": _iso(200),
            "last_validated": _iso(200),
            "last_referenced": _iso(200),
            "referenced_count": 5,
            "source_sessions": ["S-000"],
            "supersedes": [],
        },
    ]

    strategist_active = {
        "version": 1,
        "role": "strategist",
        "entries": entries_fresh + entries_stale + entries_pinned_stale,
    }
    (memory_dir / "strategist-active.json").write_text(
        json.dumps(strategist_active), encoding="utf-8"
    )

    critic_active = {"version": 1, "role": "critic", "entries": []}
    (memory_dir / "critic-active.json").write_text(
        json.dumps(critic_active), encoding="utf-8"
    )

    hub_active = {"version": 1, "role": "hub", "entries": []}
    (memory_dir / "hub-active.json").write_text(
        json.dumps(hub_active), encoding="utf-8"
    )

    return tmp_project


@pytest.fixture
def tmp_project_with_lessons(tmp_project_with_entries):
    """Project with seeded lessons.jsonl (25 entries, 3 sessions)."""
    memory_dir = Path(tmp_project_with_entries) / ".council" / "memory"
    lessons_path = memory_dir / "lessons.jsonl"

    with open(lessons_path, "w", encoding="utf-8") as f:
        for i in range(25):
            session = f"S-{(i % 3) + 1:03d}"
            lesson = {
                "ts": _iso(i * 3),
                "lesson": f"Lesson {i}: database schema migration pattern for PostgreSQL.",
                "source": "strategist" if i % 2 == 0 else "critic",
                "session": session,
            }
            f.write(json.dumps(lesson) + "\n")

    # Update topic_index to include sessions
    index_path = memory_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["topic_index"] = {
        "database": {
            "decision_ids": ["S-001", "S-002", "S-003"],
            "memory_ids": ["M-strategist-001"],
            "keywords": ["database", "schema", "migration"],
            "decisions": [],
        }
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")

    return tmp_project_with_entries
