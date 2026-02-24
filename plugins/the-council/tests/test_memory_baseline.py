"""Baseline tests — verify current behavior before any changes.

These tests must pass against the UNMODIFIED memory.py.
They serve as regression guards throughout the implementation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory import extract_topics, compute_relevance, build_memory_response, record_consultation


class TestExtractTopicsBaseline:
    def test_literal_keyword_match(self):
        topics = extract_topics("we need a database migration script")
        assert "database" in topics

    def test_unknown_text_returns_empty_or_partial(self):
        topics = extract_topics("xyz123 completely unknown words")
        # Should return empty or at most partial matches — no crash
        assert isinstance(topics, set)

    def test_multiple_topics_detected(self):
        topics = extract_topics("deploy the docker container and run tests")
        assert "infrastructure" in topics
        assert "testing" in topics


class TestComputeRelevanceBaseline:
    def test_returns_float(self):
        entry = {
            "id": "M-test-001",
            "topics": ["database"],
            "text": "Use PostgreSQL for primary storage.",
            "headline": "Use PostgreSQL.",
            "importance": 7,
            "pinned": False,
            "created": "2025-01-01T00:00:00+00:00",
            "last_referenced": "2025-01-01T00:00:00+00:00",
        }
        score = compute_relevance(entry, "database schema design")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.5  # may exceed 1.0 due to formula weights

    def test_relevant_entry_scores_higher_than_unrelated(self):
        relevant = {
            "id": "M-test-001",
            "topics": ["database"],
            "text": "PostgreSQL schema design patterns.",
            "headline": "PostgreSQL schema.",
            "importance": 5,
            "pinned": False,
            "created": "2025-01-01T00:00:00+00:00",
        }
        unrelated = {
            "id": "M-test-002",
            "topics": ["frontend"],
            "text": "React component lifecycle hooks.",
            "headline": "React lifecycle.",
            "importance": 5,
            "pinned": False,
            "created": "2025-01-01T00:00:00+00:00",
        }
        goal = "database schema migration"
        assert compute_relevance(relevant, goal) > compute_relevance(unrelated, goal)


class TestBuildMemoryResponseBaseline:
    def test_output_under_token_budget(self, tmp_project_with_entries):
        from memory import estimate_tokens
        output = build_memory_response(tmp_project_with_entries, goal="infrastructure deployment", max_tokens=2000)
        assert estimate_tokens(output) <= 2000

    def test_returns_string(self, tmp_project):
        output = build_memory_response(tmp_project, goal="test", max_tokens=4000)
        assert isinstance(output, str)
        assert len(output) > 0


class TestRecordConsultationBaseline:
    def test_writes_all_files(self, tmp_project):
        from pathlib import Path
        result = record_consultation(
            project_dir=tmp_project,
            session_id="S-baseline-001",
            goal="test baseline consultation",
            strategist_summary="Strategist recommends A.",
            critic_summary="Critic flags B.",
            decision="Adopted A with B's fix.",
            strategist_lesson="Lesson from strategist.",
            critic_lesson="Lesson from critic.",
            hub_lesson="Meta lesson from hub.",
            importance=5,
            pin=False,
        )
        memory_dir = Path(tmp_project) / ".council" / "memory"
        assert (memory_dir / "decisions.md").exists()
        assert (memory_dir / "lessons.jsonl").exists()
        assert (memory_dir / "strategist-active.json").exists()
        assert (memory_dir / "critic-active.json").exists()
        assert (memory_dir / "hub-active.json").exists()
        assert (memory_dir / "index.json").exists()
        assert "S-baseline-001" in result
