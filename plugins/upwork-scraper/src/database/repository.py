"""Async repository for CRUD operations on the jobs database."""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from ..models.job import Job, JobSummary

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class JobRepository:
    """Async repository for job data in SQLite."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert_job(self, job: Job):
        """Insert or update a job in the database."""
        await self._db.execute(
            """
            INSERT INTO jobs (
                id, url, title, description, budget_type, budget_amount,
                hourly_rate_min, hourly_rate_max, currency, experience_level,
                duration, weekly_hours, skills, category, subcategory,
                client_country, client_city, client_rating, client_total_spent,
                client_hires, client_active_jobs, client_jobs_posted,
                client_company_size, client_member_since, payment_verified,
                proposals_count, interviewing_count, invites_sent,
                connects_required, posted_date, source, search_query,
                fetched_at, raw_html
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = CASE WHEN length(excluded.description) > length(jobs.description) THEN excluded.description ELSE jobs.description END,
                budget_type = COALESCE(NULLIF(excluded.budget_type, ''), jobs.budget_type),
                budget_amount = COALESCE(excluded.budget_amount, jobs.budget_amount),
                hourly_rate_min = COALESCE(excluded.hourly_rate_min, jobs.hourly_rate_min),
                hourly_rate_max = COALESCE(excluded.hourly_rate_max, jobs.hourly_rate_max),
                experience_level = COALESCE(NULLIF(excluded.experience_level, ''), jobs.experience_level),
                skills = CASE WHEN length(excluded.skills) > 2 THEN excluded.skills ELSE jobs.skills END,
                client_rating = COALESCE(excluded.client_rating, jobs.client_rating),
                client_total_spent = COALESCE(excluded.client_total_spent, jobs.client_total_spent),
                client_hires = COALESCE(excluded.client_hires, jobs.client_hires),
                proposals_count = COALESCE(excluded.proposals_count, jobs.proposals_count),
                fetched_at = excluded.fetched_at,
                raw_html = CASE WHEN length(excluded.raw_html) > length(jobs.raw_html) THEN excluded.raw_html ELSE jobs.raw_html END
            """,
            (
                job.id, job.url, job.title, job.description, job.budget_type,
                job.budget_amount, job.hourly_rate_min, job.hourly_rate_max,
                job.currency, job.experience_level, job.duration, job.weekly_hours,
                json.dumps(job.skills), job.category, job.subcategory,
                job.client_country, job.client_city, job.client_rating,
                job.client_total_spent, job.client_hires, job.client_active_jobs,
                job.client_jobs_posted, job.client_company_size, job.client_member_since,
                1 if job.payment_verified else 0,
                job.proposals_count, job.interviewing_count, job.invites_sent,
                job.connects_required, job.posted_date, job.source, job.search_query,
                job.fetched_at, job.raw_html,
            ),
        )
        await self._db.commit()

    async def upsert_jobs(self, jobs: list[Job]):
        """Insert or update multiple jobs."""
        for job in jobs:
            await self.upsert_job(job)

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a single job by ID."""
        async with self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_job(row, cursor.description)
        return None

    async def query_jobs(
        self,
        source: str = "",
        skills_contain: str = "",
        min_budget: int = 0,
        experience_level: str = "",
        posted_within_hours: int = 0,
        sort_by: str = "fetched_at",
        limit: int = 25,
    ) -> list[JobSummary]:
        """Query jobs with filters. Returns summaries for efficiency."""
        conditions = []
        params = []

        if source:
            conditions.append("source = ?")
            params.append(source)

        if skills_contain:
            skill_list = [s.strip().lower() for s in skills_contain.split(",")]
            skill_conditions = ["LOWER(skills) LIKE ?" for _ in skill_list]
            conditions.append(f"({' OR '.join(skill_conditions)})")
            params.extend([f"%{s}%" for s in skill_list])

        if min_budget > 0:
            conditions.append("(budget_amount >= ? OR hourly_rate_min >= ?)")
            params.extend([min_budget, min_budget])

        if experience_level:
            conditions.append("LOWER(experience_level) LIKE ?")
            params.append(f"%{experience_level.lower()}%")

        if posted_within_hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=posted_within_hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sort_map = {
            "posted_date": "posted_date DESC",
            "fetched_at": "fetched_at DESC",
            "budget": "COALESCE(budget_amount, 0) DESC",
        }
        order = sort_map.get(sort_by, "fetched_at DESC")

        query = f"SELECT * FROM jobs {where} ORDER BY {order} LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                JobSummary.from_job(self._row_to_job(row, cursor.description))
                for row in rows
            ]

    async def get_stats(self) -> dict:
        """Get aggregate statistics about cached jobs."""
        stats = {}

        async with self._db.execute("SELECT COUNT(*) FROM jobs") as cursor:
            stats["total_jobs"] = (await cursor.fetchone())[0]

        async with self._db.execute(
            "SELECT COUNT(*) FROM jobs WHERE source = 'best_matches'"
        ) as cursor:
            stats["best_matches_count"] = (await cursor.fetchone())[0]

        async with self._db.execute(
            "SELECT COUNT(*) FROM jobs WHERE source = 'search'"
        ) as cursor:
            stats["search_count"] = (await cursor.fetchone())[0]

        async with self._db.execute("SELECT MAX(fetched_at) FROM jobs") as cursor:
            row = await cursor.fetchone()
            stats["last_fetch_time"] = row[0] if row[0] else None

        # Top skills
        async with self._db.execute("SELECT skills FROM jobs") as cursor:
            all_skills = Counter()
            async for row in cursor:
                try:
                    skills = json.loads(row[0]) if row[0] else []
                    for s in skills:
                        if s:
                            all_skills[s] += 1
                except json.JSONDecodeError:
                    continue
            stats["top_skills"] = dict(all_skills.most_common(20))

        # Average budget
        async with self._db.execute(
            "SELECT AVG(budget_amount) FROM jobs WHERE budget_amount > 0"
        ) as cursor:
            row = await cursor.fetchone()
            stats["avg_budget"] = round(row[0], 2) if row[0] else 0

        # Experience level breakdown
        async with self._db.execute(
            "SELECT experience_level, COUNT(*) FROM jobs WHERE experience_level != '' GROUP BY experience_level"
        ) as cursor:
            stats["experience_breakdown"] = {row[0]: row[1] async for row in cursor}

        return stats

    async def get_skill_counts(self, limit: int = 30) -> list[tuple[str, int]]:
        """Get skill frequency counts across all jobs."""
        async with self._db.execute("SELECT skills FROM jobs") as cursor:
            counter = Counter()
            async for row in cursor:
                try:
                    skills = json.loads(row[0]) if row[0] else []
                    for s in skills:
                        if s:
                            counter[s] += 1
                except json.JSONDecodeError:
                    continue
        return counter.most_common(limit)

    async def get_job_count(self) -> int:
        """Get total number of cached jobs."""
        async with self._db.execute("SELECT COUNT(*) FROM jobs") as cursor:
            return (await cursor.fetchone())[0]

    def _row_to_job(self, row: tuple, description) -> Job:
        """Convert a database row to a Job model."""
        col_names = [d[0] for d in description]
        data = dict(zip(col_names, row))

        # Parse JSON fields
        if isinstance(data.get("skills"), str):
            try:
                data["skills"] = json.loads(data["skills"])
            except json.JSONDecodeError:
                data["skills"] = []

        # Convert integer boolean
        data["payment_verified"] = bool(data.get("payment_verified", 0))

        return Job(**data)
