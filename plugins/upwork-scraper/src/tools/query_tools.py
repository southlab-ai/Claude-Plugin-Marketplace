"""MCP tools for querying locally cached job data (instant, no scraping)."""

from __future__ import annotations

import json

import aiosqlite

from ..config import DB_PATH
from ..database.models import initialize_db
from ..database.repository import JobRepository


async def _get_repo() -> tuple[aiosqlite.Connection, JobRepository]:
    """Get a database connection and repository."""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await initialize_db(db)
    return db, JobRepository(db)


async def list_cached_jobs(
    source: str = "",
    skills_contain: str = "",
    min_budget: int = 0,
    experience_level: str = "",
    posted_within_hours: int = 0,
    sort_by: str = "fetched_at",
    limit: int = 25,
) -> str:
    """Query locally cached jobs without hitting Upwork.

    Returns jobs from the local database that were previously
    fetched via fetch_best_matches or search_jobs. Useful for
    filtering and re-analyzing previously scraped data.

    Args:
        source: "best_matches", "search", or "" for all.
        skills_contain: Comma-separated skills to filter by
            (e.g. "python,fastapi"). Matches if job has ANY listed skill.
        min_budget: Minimum budget filter in USD.
        experience_level: "entry", "intermediate", "expert", or "".
        posted_within_hours: Only jobs fetched within N hours (0=all).
        sort_by: "posted_date", "budget", or "fetched_at" (default).
        limit: Max results to return (default 25).

    Returns:
        JSON list of job summaries from local cache.
    """
    db, repo = await _get_repo()
    try:
        jobs = await repo.query_jobs(
            source=source,
            skills_contain=skills_contain,
            min_budget=min_budget,
            experience_level=experience_level,
            posted_within_hours=posted_within_hours,
            sort_by=sort_by,
            limit=limit,
        )

        if not jobs:
            return "No cached jobs found matching your filters. Try fetching jobs first."

        lines = [f"Found {len(jobs)} cached jobs:\n"]
        for i, job in enumerate(jobs, 1):
            budget = ""
            if job.budget_amount:
                budget = f"${job.budget_amount:,.0f}"
            elif job.hourly_rate_min:
                budget = f"${job.hourly_rate_min}-${job.hourly_rate_max or '?'}/hr"

            skills = ", ".join(job.skills[:5])
            lines.append(
                f"{i}. **{job.title}**\n"
                f"   Budget: {budget or 'N/A'} | "
                f"Level: {job.experience_level or 'N/A'} | "
                f"Source: {job.source}\n"
                f"   Skills: {skills or 'None'}\n"
                f"   URL: {job.url}\n"
            )

        return "\n".join(lines)
    finally:
        await db.close()


async def get_scraping_stats() -> str:
    """Get statistics about the local job database.

    Returns total jobs, breakdown by source, top skills,
    average budget, experience level distribution, and last fetch time.

    Returns:
        JSON with database statistics.
    """
    db, repo = await _get_repo()
    try:
        stats = await repo.get_stats()
        return json.dumps(stats, indent=2)
    finally:
        await db.close()
