"""MCP Server entry point for the Upwork Job Scraper plugin.

Exposes 11 tools to Claude Code via the Model Context Protocol:
- Session management: start_session, session_status, check_auth, stop_session
- Scraping: fetch_best_matches, search_jobs, get_job_details
- Query: list_cached_jobs, get_scraping_stats
- Analysis: analyze_market_requirements, suggest_portfolio_projects

The Session Manager HTTP service (aiohttp on localhost:8024) is auto-started
as part of the MCP server lifecycle — no separate process needed.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from aiohttp.web import AppRunner, TCPSite
from mcp.server.fastmcp import FastMCP

from .config import SESSION_MANAGER_HOST, SESSION_MANAGER_PORT, ensure_dirs
from .tools.analysis_tools import analyze_market_requirements, suggest_portfolio_projects
from .tools.query_tools import get_scraping_stats, list_cached_jobs
from .tools.scraping_tools import fetch_best_matches, get_job_details, search_jobs
from .tools.session_tools import check_auth, session_status, start_session, stop_session

# Configure logging to stderr (stdout is reserved for MCP JSON-RPC)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("upwork-scraper")

# Ensure data directories exist
ensure_dirs()


# ── Lifespan: auto-start Session Manager ─────────────────────────────────────


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Start the Session Manager HTTP service alongside the MCP server."""
    from .session_manager.manager import create_app

    app = create_app()
    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, SESSION_MANAGER_HOST, SESSION_MANAGER_PORT)
    managed = False
    try:
        await site.start()
        logger.info(
            "Session Manager auto-started on %s:%s", SESSION_MANAGER_HOST, SESSION_MANAGER_PORT
        )
        managed = True
    except OSError:
        # Port already in use — assume Session Manager was started manually
        logger.info(
            "Session Manager already running on %s:%s", SESSION_MANAGER_HOST, SESSION_MANAGER_PORT
        )
        await runner.cleanup()

    try:
        yield {}
    finally:
        if managed:
            await runner.cleanup()
            logger.info("Session Manager stopped.")


# ── MCP Server ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    "upwork-scraper",
    lifespan=lifespan,
    instructions=(
        "Upwork Job Scraper - Tools to search and analyze Upwork job listings. "
        "The Session Manager starts automatically with this server. "
        "Call session_status to check if a browser session is active. "
        "If not, call start_session to launch the browser for login. "
        "Once authenticated, use fetch_best_matches or search_jobs to scrape listings. "
        "Use list_cached_jobs and get_scraping_stats to query previously fetched data. "
        "Use analyze_market_requirements and suggest_portfolio_projects for insights."
    ),
)


# ── Session Management Tools ─────────────────────────────────────────────────


@mcp.tool()
async def tool_start_session(headless: bool = False) -> str:
    """Start the Upwork browser session.

    Launches the Camoufox anti-detection browser and attempts to restore
    a previous session. If no valid session exists, opens a browser window
    for manual login. Set headless=False (default) to see the browser.

    Args:
        headless: If False, opens visible browser for CAPTCHA solving.
    """
    return await start_session(headless)


@mcp.tool()
async def tool_session_status() -> str:
    """Check if the Upwork session is active.

    Returns: session state, cookie count, cached jobs, last scrape time.
    """
    return await session_status()


@mcp.tool()
async def tool_check_auth() -> str:
    """Verify authentication after user completes login.

    Call this after the user says they've logged in and solved CAPTCHAs.
    """
    return await check_auth()


@mcp.tool()
async def tool_stop_session() -> str:
    """Stop the browser session. Saves cookies, cached data remains available."""
    return await stop_session()


# ── Scraping Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def tool_fetch_best_matches(max_jobs: int = 20, force_refresh: bool = False) -> str:
    """Fetch your personalized Upwork 'Best Matches'.

    Requires an active session. Scrolls the Best Matches page to load jobs,
    fetches full details, and caches results locally.

    Args:
        max_jobs: Maximum jobs to fetch (1-50, default 20).
        force_refresh: Re-fetch even if cached data is recent.
    """
    return await fetch_best_matches(max_jobs, force_refresh)


@mcp.tool()
async def tool_search_jobs(
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
    """Search Upwork jobs with filters.

    Supports boolean queries: "python AND (Django OR Flask)".

    Args:
        query: Search keywords.
        category: e.g. "Web, Mobile & Software Dev".
        experience_level: "entry", "intermediate", or "expert".
        job_type: "hourly" or "fixed".
        budget_min: Minimum budget USD (0=none).
        budget_max: Maximum budget USD (0=none).
        client_hires: Client hire count: "1-9" or "10+".
        proposals: Max proposals: "0-4", "5-9", etc.
        hours_per_week: "less_than_30" or "more_than_30".
        project_length: "week", "month", "semester", "ongoing".
        sort_by: "relevance" or "recency".
        max_results: Max jobs (1-100, default 20).
    """
    return await search_jobs(
        query, category, experience_level, job_type,
        budget_min, budget_max, client_hires, proposals,
        hours_per_week, project_length, sort_by, max_results,
    )


@mcp.tool()
async def tool_get_job_details(job_url: str) -> str:
    """Get complete details for a specific Upwork job.

    Fetches 60+ fields: full description, client history, budget, skills, etc.

    Args:
        job_url: Full Upwork URL or job ID (~0xxxxx).
    """
    return await get_job_details(job_url)


# ── Query Tools (instant, from local cache) ──────────────────────────────────


@mcp.tool()
async def tool_list_cached_jobs(
    source: str = "",
    skills_contain: str = "",
    min_budget: int = 0,
    experience_level: str = "",
    posted_within_hours: int = 0,
    sort_by: str = "fetched_at",
    limit: int = 25,
) -> str:
    """Query locally cached jobs (instant, no Upwork request).

    Filter and browse jobs previously fetched via best_matches or search.

    Args:
        source: "best_matches", "search", or "" for all.
        skills_contain: Comma-separated skills filter (matches ANY).
        min_budget: Minimum budget USD.
        experience_level: "entry", "intermediate", "expert".
        posted_within_hours: Only recent jobs (0=all).
        sort_by: "posted_date", "budget", or "fetched_at".
        limit: Max results (default 25).
    """
    return await list_cached_jobs(
        source, skills_contain, min_budget, experience_level,
        posted_within_hours, sort_by, limit,
    )


@mcp.tool()
async def tool_get_scraping_stats() -> str:
    """Get statistics about the cached job database.

    Returns: total jobs, top skills, avg budget, experience breakdown.
    """
    return await get_scraping_stats()


# ── Analysis Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def tool_analyze_market_requirements(
    skill_focus: str = "",
    top_n: int = 20,
) -> str:
    """Analyze job market requirements from cached data.

    Aggregates skills demand, budget ranges, experience levels.

    Args:
        skill_focus: Focus on a specific skill (e.g. "python"). Empty=all.
        top_n: Top items per category (default 20).
    """
    return await analyze_market_requirements(skill_focus, top_n)


@mcp.tool()
async def tool_suggest_portfolio_projects(
    your_skills: str,
    target_experience_level: str = "intermediate",
    top_n: int = 5,
) -> str:
    """Suggest portfolio projects based on market demand.

    Cross-references your skills with job requirements to suggest
    open-source projects as your 'carta de presentacion'.

    Args:
        your_skills: Comma-separated skills (e.g. "python,fastapi,react").
        target_experience_level: "entry", "intermediate", or "expert".
        top_n: Number of suggestions (default 5).
    """
    return await suggest_portfolio_projects(your_skills, target_experience_level, top_n)


# ── Entry Point ──────────────────────────────────────────────────────────────


def main():
    """Run the MCP server on STDIO transport."""
    logger.info("Starting Upwork Scraper MCP server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
