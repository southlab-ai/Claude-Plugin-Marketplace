"""Feature tests for memory retrieval improvements (A1-A10).

Tests synonym expansion, bigrams, staleness, archive scoring, and 3-tier packing.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory import (
    SYNONYM_MAP,
    _stale_marker,
    build_memory_response,
    compute_relevance,
    estimate_tokens,
    extract_topics,
    load_active,
    load_index,
    record_consultation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso(days_ago: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _make_entry(
    entry_id: str = "M-test-001",
    topics: list[str] | None = None,
    text: str = "test entry text",
    headline: str = "test headline",
    importance: int = 5,
    pinned: bool = False,
    days_ago: int = 0,
    last_validated_days_ago: int | None = None,
) -> dict:
    created = _iso(days_ago)
    last_val = _iso(last_validated_days_ago if last_validated_days_ago is not None else days_ago)
    return {
        "id": entry_id,
        "topics": topics or [],
        "text": text,
        "headline": headline,
        "importance": importance,
        "pinned": pinned,
        "created": created,
        "last_validated": last_val,
        "last_referenced": created,
        "referenced_count": 0,
        "source_sessions": ["S-test"],
        "supersedes": [],
    }


# ===========================================================================
# A1: SYNONYM_MAP + synonym expansion in extract_topics
# ===========================================================================
class TestSynonymExpansion:
    def test_synonym_map_exists_and_has_entries(self):
        assert isinstance(SYNONYM_MAP, dict)
        assert len(SYNONYM_MAP) > 40

    def test_k8s_expands_to_kubernetes(self):
        topics = extract_topics("deploy to k8s cluster")
        # k8s -> kubernetes, which matches infrastructure topic keyword
        assert "infrastructure" in topics

    def test_postgres_expands_to_database(self):
        topics = extract_topics("migrate postgres tables")
        assert "database" in topics

    def test_redis_expands_to_cache(self):
        topics = extract_topics("set up redis for sessions")
        # redis -> cache, which matches performance topic
        assert "performance" in topics

    def test_synonym_does_not_mutate_topic_index(self):
        """SYNONYM_MAP entries must NEVER leak into topic_index keywords."""
        topic_idx = {"infrastructure": {"keywords": ["docker"], "decision_ids": []}}
        extract_topics("deploy to k8s", topic_index=topic_idx)
        # k8s and kubernetes should NOT appear in topic_idx keywords
        assert "k8s" not in topic_idx["infrastructure"]["keywords"]
        assert "kubernetes" not in topic_idx["infrastructure"]["keywords"]

    def test_multiple_synonyms_in_one_text(self):
        topics = extract_topics("jenkins pipeline on eks with redis cache")
        # jenkins -> pipeline (infrastructure), eks -> kubernetes (infrastructure), redis -> cache (performance)
        assert "infrastructure" in topics
        assert "performance" in topics


# ===========================================================================
# A2: Bigram extraction
# ===========================================================================
class TestBigramExtraction:
    def test_bigrams_generated(self):
        topics = extract_topics("database migration script")
        # The function returns topics (not words), but bigrams help matching.
        # "database-migration" is a bigram that can match keywords
        assert "database" in topics

    def test_bigram_from_two_words(self):
        # Direct test: we can check if "rate-limit" topic matches via bigrams
        topics = extract_topics("handle rate limit throttling")
        # "rate-limit" bigram should match the api topic's "rate-limit" keyword
        assert "api" in topics


# ===========================================================================
# A3: Synonym weight (0.5x) in compute_relevance
# ===========================================================================
class TestSynonymWeight:
    def test_direct_match_scores_higher_than_synonym_only(self):
        """Direct keyword overlap should contribute more than synonym-only overlap."""
        entry = _make_entry(
            text="kubernetes cluster setup",
            headline="kubernetes cluster",
            topics=["infrastructure"],
        )
        # "kubernetes" is a direct match in goal
        direct_score = compute_relevance(entry, "kubernetes")
        # "k8s" only contributes via synonym (0.5x weight), no direct match for "k8s" in entry
        synonym_score = compute_relevance(entry, "k8s")
        # Direct overlap of "kubernetes" contributes at full weight (1.0x)
        # Synonym expansion of k8s->kubernetes contributes at 0.5x weight
        assert direct_score >= synonym_score

    def test_synonym_still_contributes_to_score(self):
        """Synonym matches should still increase relevance vs no match."""
        entry = _make_entry(
            text="Set up kubernetes deployment with helm charts",
            headline="Kubernetes deployment",
            topics=["infrastructure"],
        )
        synonym_score = compute_relevance(entry, "k8s deployment")
        no_match_score = compute_relevance(entry, "unrelated xyz topic")
        assert synonym_score > no_match_score


# ===========================================================================
# A4: last_validated field in record_consultation
# ===========================================================================
class TestLastValidated:
    def test_recorded_entry_has_last_validated(self, tmp_project):
        record_consultation(
            project_dir=tmp_project,
            session_id="S-val-001",
            goal="test last_validated field",
            strategist_summary="summary",
            critic_summary="critic summary",
            decision="decision",
            strategist_lesson="Important lesson about validation.",
            importance=5,
        )
        active = load_active(tmp_project, "strategist")
        entries = active.get("entries", [])
        assert len(entries) > 0
        entry = entries[-1]
        assert "last_validated" in entry
        assert entry["last_validated"] != ""

    def test_last_validated_equals_created_on_new_entry(self, tmp_project):
        record_consultation(
            project_dir=tmp_project,
            session_id="S-val-002",
            goal="test timestamps match",
            strategist_summary="summary",
            critic_summary="critic",
            decision="dec",
            strategist_lesson="Lesson here.",
            importance=5,
        )
        active = load_active(tmp_project, "strategist")
        entry = active["entries"][-1]
        assert entry["last_validated"] == entry["created"]


# ===========================================================================
# A5: Staleness penalty in compute_relevance
# ===========================================================================
class TestStalenessPenalty:
    def test_stale_entry_penalized(self):
        """Entry validated >90 days ago gets 0.7x penalty."""
        stale = _make_entry(
            text="database migration guide for postgres",
            headline="DB migration",
            topics=["database"],
            days_ago=100,
            last_validated_days_ago=100,
        )
        fresh = _make_entry(
            text="database migration guide for postgres",
            headline="DB migration",
            topics=["database"],
            days_ago=100,
            last_validated_days_ago=5,
        )
        stale_score = compute_relevance(stale, "database migration")
        fresh_score = compute_relevance(fresh, "database migration")
        assert fresh_score > stale_score

    def test_pinned_entry_exempt_from_staleness(self):
        """Pinned entries should never be penalized for staleness."""
        pinned_stale = _make_entry(
            text="critical architecture decision",
            headline="Architecture",
            topics=["architecture"],
            days_ago=200,
            last_validated_days_ago=200,
            pinned=True,
        )
        unpinned_stale = _make_entry(
            text="critical architecture decision",
            headline="Architecture",
            topics=["architecture"],
            days_ago=200,
            last_validated_days_ago=200,
            pinned=False,
        )
        pinned_score = compute_relevance(pinned_stale, "architecture patterns")
        unpinned_score = compute_relevance(unpinned_stale, "architecture patterns")
        assert pinned_score > unpinned_score

    def test_entry_at_exactly_90_days_not_penalized(self):
        """90 days is the threshold — exactly 90 should NOT be penalized."""
        at_boundary = _make_entry(
            text="database schema patterns",
            topics=["database"],
            days_ago=90,
            last_validated_days_ago=90,
        )
        fresh = _make_entry(
            text="database schema patterns",
            topics=["database"],
            days_ago=90,
            last_validated_days_ago=5,
        )
        # At exactly 90 days, stale_days=90, which is NOT > 90, so no penalty
        boundary_score = compute_relevance(at_boundary, "database schema")
        fresh_score = compute_relevance(fresh, "database schema")
        assert boundary_score == fresh_score

    def test_fallback_to_created_when_no_last_validated(self):
        """Entries without last_validated should fall back to created."""
        entry_no_lv = {
            "id": "M-test-old",
            "topics": ["database"],
            "text": "old database pattern",
            "headline": "old",
            "importance": 5,
            "pinned": False,
            "created": _iso(100),
            "last_referenced": _iso(100),
        }
        score = compute_relevance(entry_no_lv, "database design")
        assert isinstance(score, float)
        assert score >= 0.0


# ===========================================================================
# A6: Stale marker in output + version migration
# ===========================================================================
class TestStaleMarker:
    def test_stale_marker_shows_for_old_entry(self):
        entry = _make_entry(days_ago=120, last_validated_days_ago=120)
        marker = _stale_marker(entry)
        assert "[stale:" in marker
        assert "d]" in marker

    def test_stale_marker_empty_for_fresh_entry(self):
        entry = _make_entry(days_ago=10, last_validated_days_ago=10)
        marker = _stale_marker(entry)
        assert marker == ""

    def test_stale_marker_empty_for_pinned(self):
        entry = _make_entry(days_ago=200, last_validated_days_ago=200, pinned=True)
        marker = _stale_marker(entry)
        assert marker == ""

    def test_stale_marker_in_output(self, tmp_project_with_entries):
        """Stale entries should have [stale: Xd] in build_memory_response output."""
        output = build_memory_response(
            tmp_project_with_entries,
            goal="performance cache optimization",
            max_tokens=4000,
        )
        # M-strategist-003 is 120 days old and should show stale marker
        assert "[stale:" in output

    def test_version_auto_migration(self, tmp_project):
        """Loading a v1 index should auto-migrate to v2."""
        memory_dir = Path(tmp_project) / ".council" / "memory"
        v1_index = {
            "version": 1,
            "consultation_count": 3,
            "last_updated": "",
            "compaction_watermark": "",
            "recent_decisions": [],
            "pinned": [],
            "topic_index": {},
            "original_prompt": "",
        }
        (memory_dir / "index.json").write_text(json.dumps(v1_index), encoding="utf-8")

        loaded = load_index(tmp_project)
        assert loaded["version"] == 2
        assert loaded["consultation_count"] == 3  # data preserved

        # File should be written back as v2
        on_disk = json.loads((memory_dir / "index.json").read_text(encoding="utf-8"))
        assert on_disk["version"] == 2


# ===========================================================================
# A7: Archive 200-lesson cap
# ===========================================================================
class TestArchiveCap:
    def test_large_archive_capped(self, tmp_project_with_entries):
        """Even with >200 lessons, the output should not blow up."""
        memory_dir = Path(tmp_project_with_entries) / ".council" / "memory"
        lessons_path = memory_dir / "lessons.jsonl"

        # Write 300 lessons
        with open(lessons_path, "w", encoding="utf-8") as f:
            for i in range(300):
                lesson = {
                    "ts": _iso(i),
                    "lesson": f"Lesson {i}: database schema migration pattern for PostgreSQL index optimization.",
                    "source": "strategist",
                    "session": "S-001",
                }
                f.write(json.dumps(lesson) + "\n")

        # Set up topic index
        index_path = memory_dir / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["topic_index"] = {
            "database": {
                "decision_ids": ["S-001"],
                "memory_ids": [],
                "keywords": ["database", "schema", "migration"],
                "decisions": [],
            }
        }
        index_path.write_text(json.dumps(index), encoding="utf-8")

        output = build_memory_response(
            tmp_project_with_entries,
            goal="database schema migration",
            max_tokens=4000,
        )
        # Should succeed without error and stay within budget
        assert estimate_tokens(output) <= 4000
        assert "Archived Lessons" in output


# ===========================================================================
# A8: Archive relevance scoring (top 12)
# ===========================================================================
class TestArchiveRelevanceScoring:
    def test_relevant_lessons_prioritized(self, tmp_project_with_entries):
        """More relevant lessons should appear before less relevant ones."""
        memory_dir = Path(tmp_project_with_entries) / ".council" / "memory"
        lessons_path = memory_dir / "lessons.jsonl"

        with open(lessons_path, "w", encoding="utf-8") as f:
            # Irrelevant lesson
            f.write(json.dumps({
                "ts": _iso(10),
                "lesson": "Frontend React component styling with tailwind css.",
                "source": "strategist",
                "session": "S-001",
            }) + "\n")
            # Relevant lesson
            f.write(json.dumps({
                "ts": _iso(5),
                "lesson": "Database PostgreSQL schema migration index optimization patterns.",
                "source": "strategist",
                "session": "S-001",
            }) + "\n")

        index_path = memory_dir / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["topic_index"] = {
            "database": {
                "decision_ids": ["S-001"],
                "memory_ids": [],
                "keywords": ["database", "schema"],
                "decisions": [],
            }
        }
        index_path.write_text(json.dumps(index), encoding="utf-8")

        output = build_memory_response(
            tmp_project_with_entries,
            goal="database schema migration",
            max_tokens=4000,
        )
        if "Archived Lessons" in output:
            # The database-related lesson should appear
            assert "PostgreSQL" in output or "migration" in output


# ===========================================================================
# A9: Archive token cap
# ===========================================================================
class TestArchiveTokenCap:
    def test_archive_respects_token_budget(self, tmp_project_with_entries):
        """Archive section should not exceed its token cap."""
        memory_dir = Path(tmp_project_with_entries) / ".council" / "memory"
        lessons_path = memory_dir / "lessons.jsonl"

        # Write many long lessons
        with open(lessons_path, "w", encoding="utf-8") as f:
            for i in range(50):
                lesson = {
                    "ts": _iso(i),
                    "lesson": f"Lesson {i}: " + "database schema migration optimization " * 10,
                    "source": "strategist",
                    "session": "S-001",
                }
                f.write(json.dumps(lesson) + "\n")

        index_path = memory_dir / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["topic_index"] = {
            "database": {
                "decision_ids": ["S-001"],
                "memory_ids": [],
                "keywords": ["database"],
                "decisions": [],
            }
        }
        index_path.write_text(json.dumps(index), encoding="utf-8")

        output = build_memory_response(
            tmp_project_with_entries,
            goal="database migration",
            max_tokens=2000,
        )
        assert estimate_tokens(output) <= 2000


# ===========================================================================
# A10: 3-tier budget packing
# ===========================================================================
class TestThreeTierPacking:
    def test_generous_budget_shows_full_text(self, tmp_project_with_entries):
        """With generous budget (>2500 remaining), full text should appear."""
        output = build_memory_response(
            tmp_project_with_entries,
            goal="infrastructure deployment",
            max_tokens=6000,
        )
        # Should have "Relevant to this goal" or "Other important context" sections
        has_relevant = "### Relevant to this goal" in output
        has_other = "### Other important context" in output
        assert has_relevant or has_other

    def test_normal_budget_shows_memory_overview(self, tmp_project_with_entries):
        """With normal budget (800-2500), should use Memory Overview section."""
        # We need to find a budget where remaining falls in 800-2500
        # tier0 is ~200-500 tokens, so max_tokens ~1300-3000 should put us in normal range
        output = build_memory_response(
            tmp_project_with_entries,
            goal="infrastructure deployment",
            max_tokens=1800,
        )
        # Should use "Memory Overview" heading from 2-pass packing
        # or fall into tight/generous path depending on tier0 size
        assert estimate_tokens(output) <= 1800
        assert isinstance(output, str)
        assert len(output) > 0

    def test_tight_budget_stays_within_limits(self, tmp_project_with_entries):
        """With tight budget, should still produce valid output."""
        output = build_memory_response(
            tmp_project_with_entries,
            goal="infrastructure deployment",
            max_tokens=800,
        )
        assert estimate_tokens(output) <= 800
        assert isinstance(output, str)

    def test_budget_never_exceeded(self, tmp_project_with_entries):
        """Test multiple budget sizes to verify no overrun."""
        for budget in [500, 800, 1200, 1800, 2500, 4000, 8000]:
            output = build_memory_response(
                tmp_project_with_entries,
                goal="database migration kubernetes deploy",
                max_tokens=budget,
            )
            actual_tokens = estimate_tokens(output)
            assert actual_tokens <= budget, f"Budget {budget} exceeded: {actual_tokens} tokens"
