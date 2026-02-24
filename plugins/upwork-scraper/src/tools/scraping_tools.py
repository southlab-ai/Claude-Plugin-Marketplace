"""MCP tools for scraping Upwork job listings."""

from __future__ import annotations

import json

from ..config import SESSION_MANAGER_URL
from .session_tools import _call_session_manager


async def fetch_best_matches(max_jobs: int = 20, force_refresh: bool = False) -> str:
    """Fetch your personalized 'Best Matches' from Upwork.

    Requires an active session. Navigates to your Best Matches page,
    scrolls to load jobs, then fetches full details for each.
    Results are saved to the local database.

    Args:
        max_jobs: Maximum number of jobs to fetch (1-50, default 20).
        force_refresh: If True, re-fetches even if data is recent.

    Returns:
        JSON with job summaries: title, budget, skills, experience, posted date.
    """
    result = await _call_session_manager(
        "POST",
        "/scrape/best-matches",
        {"max_jobs": max_jobs},
    )

    if "error" in result:
        return f"Error: {result['error']}"

    count = result.get("count", 0)
    jobs = result.get("jobs", [])

    if count == 0:
        return "No Best Matches found. Make sure your Upwork profile is complete."

    # Format for readable output
    lines = [f"Found {count} Best Matches:\n"]
    for i, job in enumerate(jobs, 1):
        budget = ""
        if job.get("budget_amount"):
            budget = f"${job['budget_amount']:,.0f}"
        elif job.get("hourly_rate_min"):
            budget = f"${job['hourly_rate_min']}-${job.get('hourly_rate_max', '?')}/hr"

        skills = ", ".join(job.get("skills", [])[:5])
        lines.append(
            f"{i}. **{job.get('title', 'Untitled')}**\n"
            f"   Budget: {budget or 'Not specified'} | "
            f"Level: {job.get('experience_level', 'N/A')} | "
            f"Proposals: {job.get('proposals_count', 'N/A')}\n"
            f"   Skills: {skills or 'None listed'}\n"
            f"   URL: {job.get('url', '')}\n"
        )

    return "\n".join(lines)


async def search_jobs(
    query: str,
    category: str = "",
    experience_level: str = "",
    job_type: str = "",
    budget_min: int = 0,
    budget_max: int = 0,
    client_hires: str = "",
    proposals: str = "",
    hours_per_week: str = "",
    project_length: str = "",
    sort_by: str = "relevance",
    max_results: int = 20,
) -> str:
    """Search Upwork job listings with filters.

    Requires an active session for full results.

    Args:
        query: Search keywords (e.g. "python fastapi developer").
            Supports boolean: "python AND (Django OR Flask)".
        category: Upwork category (e.g. "Web, Mobile & Software Dev").
        experience_level: "entry", "intermediate", or "expert".
        job_type: "hourly" or "fixed".
        budget_min: Minimum budget in USD (0 = no minimum).
        budget_max: Maximum budget in USD (0 = no maximum).
        client_hires: Filter by client hire count: "1-9", "10+".
        proposals: Max proposals: "0-4", "5-9", "10-14".
        hours_per_week: "less_than_30" or "more_than_30".
        project_length: "week", "month", "semester", "ongoing".
        sort_by: "relevance" (default) or "recency".
        max_results: Max jobs to return (1-100, default 20).

    Returns:
        JSON with job summaries matching search criteria.
    """
    params = {
        "query": query,
        "category": category,
        "experience_level": experience_level,
        "job_type": job_type,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "client_hires": client_hires,
        "proposals": proposals,
        "hours_per_week": hours_per_week,
        "project_length": project_length,
        "sort_by": sort_by,
        "max_results": max_results,
    }

    result = await _call_session_manager("POST", "/scrape/search", params)

    if "error" in result:
        return f"Error: {result['error']}"

    count = result.get("count", 0)
    jobs = result.get("jobs", [])

    if count == 0:
        return f"No jobs found for query: '{query}'"

    lines = [f"Found {count} jobs for '{query}':\n"]
    for i, job in enumerate(jobs, 1):
        budget = ""
        if job.get("budget_amount"):
            budget = f"${job['budget_amount']:,.0f}"
        elif job.get("hourly_rate_min"):
            budget = f"${job['hourly_rate_min']}-${job.get('hourly_rate_max', '?')}/hr"

        skills = ", ".join(job.get("skills", [])[:5])
        lines.append(
            f"{i}. **{job.get('title', 'Untitled')}**\n"
            f"   Budget: {budget or 'Not specified'} | "
            f"Level: {job.get('experience_level', 'N/A')} | "
            f"Proposals: {job.get('proposals_count', 'N/A')}\n"
            f"   Skills: {skills or 'None listed'}\n"
            f"   URL: {job.get('url', '')}\n"
        )

    return "\n".join(lines)


async def get_job_details(job_url: str) -> str:
    """Fetch complete details for a specific Upwork job posting.

    Retrieves all available fields including description, client
    history, budget, required skills, and proposal activity.

    Args:
        job_url: Full Upwork job URL or job ID (the ~0xxxxx part).

    Returns:
        JSON with all job fields.
    """
    result = await _call_session_manager(
        "POST",
        "/scrape/job-detail",
        {"job_url": job_url},
    )

    if "error" in result:
        return f"Error: {result['error']}"

    job = result.get("job", {})
    return json.dumps(job, indent=2)
