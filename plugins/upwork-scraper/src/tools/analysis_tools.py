"""MCP tools for analyzing job market data and suggesting portfolio projects."""

from __future__ import annotations

import json
from collections import Counter

import aiosqlite

from ..config import DB_PATH
from ..database.models import initialize_db
from ..database.repository import JobRepository


async def _get_repo() -> tuple[aiosqlite.Connection, JobRepository]:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await initialize_db(db)
    return db, JobRepository(db)


async def analyze_market_requirements(
    skill_focus: str = "",
    top_n: int = 20,
) -> str:
    """Analyze job market requirements from cached Upwork data.

    Aggregates data across all cached jobs to identify trends in
    required skills, budget ranges, experience levels, and common
    job description patterns.

    Args:
        skill_focus: Optional skill to focus analysis on
            (e.g. "python"). If empty, analyzes all jobs.
        top_n: Number of top items per category (default 20).

    Returns:
        JSON with market analysis: top skills, budget distribution,
        experience breakdown, job type split, and common requirements.
    """
    db, repo = await _get_repo()
    try:
        # Get filtered jobs
        jobs = await repo.query_jobs(
            skills_contain=skill_focus,
            limit=500,
        )

        if not jobs:
            return json.dumps({
                "error": "No cached jobs found. Fetch some jobs first.",
                "total_jobs_analyzed": 0,
            })

        # Aggregate skills
        skill_counter = Counter()
        budget_amounts = []
        hourly_rates_min = []
        hourly_rates_max = []
        experience_counts = Counter()
        type_counts = Counter()
        category_counter = Counter()

        for job in jobs:
            for skill in job.skills:
                skill_counter[skill] += 1

            if job.budget_amount and job.budget_amount > 0:
                budget_amounts.append(job.budget_amount)
            if job.hourly_rate_min and job.hourly_rate_min > 0:
                hourly_rates_min.append(job.hourly_rate_min)
            if job.hourly_rate_max and job.hourly_rate_max > 0:
                hourly_rates_max.append(job.hourly_rate_max)

            if job.experience_level:
                experience_counts[job.experience_level] += 1

            # Infer type from budget fields
            if job.hourly_rate_min:
                type_counts["hourly"] += 1
            elif job.budget_amount:
                type_counts["fixed"] += 1

        total = len(jobs)

        # Top skills
        top_skills = [
            {"skill": skill, "count": count, "percentage": round(count / total * 100, 1)}
            for skill, count in skill_counter.most_common(top_n)
        ]

        # Budget distribution
        budget_buckets = [
            ("$0-$100", 0, 100),
            ("$100-$500", 100, 500),
            ("$500-$1K", 500, 1000),
            ("$1K-$5K", 1000, 5000),
            ("$5K-$10K", 5000, 10000),
            ("$10K+", 10000, float("inf")),
        ]
        budget_dist = []
        for label, low, high in budget_buckets:
            count = sum(1 for b in budget_amounts if low <= b < high)
            if count > 0:
                budget_dist.append({
                    "range": label,
                    "count": count,
                    "percentage": round(count / max(len(budget_amounts), 1) * 100, 1),
                })

        analysis = {
            "total_jobs_analyzed": total,
            "skill_focus": skill_focus or "all",
            "top_skills": top_skills,
            "budget_distribution": budget_dist,
            "experience_breakdown": dict(experience_counts),
            "job_type_split": dict(type_counts),
            "avg_hourly_rate_min": round(sum(hourly_rates_min) / max(len(hourly_rates_min), 1), 2),
            "avg_hourly_rate_max": round(sum(hourly_rates_max) / max(len(hourly_rates_max), 1), 2),
            "avg_fixed_budget": round(sum(budget_amounts) / max(len(budget_amounts), 1), 2),
        }

        return json.dumps(analysis, indent=2)

    finally:
        await db.close()


async def suggest_portfolio_projects(
    your_skills: str,
    target_experience_level: str = "intermediate",
    top_n: int = 5,
) -> str:
    """Suggest open-source portfolio projects based on market demand.

    Cross-references your skills with the most in-demand job
    requirements to suggest portfolio projects that would serve
    as an effective showcase for Upwork clients.

    Args:
        your_skills: Comma-separated list of your skills
            (e.g. "python,fastapi,react,postgresql").
        target_experience_level: Target job tier: "entry",
            "intermediate", or "expert".
        top_n: Number of project suggestions (default 5).

    Returns:
        JSON array of project suggestions with: project name,
        description, skills demonstrated, matching job count,
        sample job titles, estimated complexity, tech stack.
    """
    db, repo = await _get_repo()
    try:
        my_skills = [s.strip().lower() for s in your_skills.split(",") if s.strip()]

        if not my_skills:
            return json.dumps({"error": "Please provide your skills as comma-separated values."})

        # Get all jobs and find skill combinations
        all_jobs = await repo.query_jobs(limit=500)

        if not all_jobs:
            return json.dumps({
                "error": "No cached jobs. Fetch jobs first to generate portfolio suggestions.",
            })

        # Find skill combos that appear together in jobs
        skill_combos = Counter()
        matching_jobs = []

        for job in all_jobs:
            job_skills_lower = [s.lower() for s in job.skills]
            # Check overlap with user skills
            overlap = set(my_skills) & set(job_skills_lower)
            if overlap:
                matching_jobs.append(job)
                # Track non-overlap skills (gaps = learning opportunities)
                combo_key = frozenset(job_skills_lower[:8])
                skill_combos[combo_key] += 1

        # Identify top demanded skill combinations that match user skills
        top_combos = skill_combos.most_common(top_n * 2)

        suggestions = []
        seen_themes = set()

        for combo, count in top_combos:
            if len(suggestions) >= top_n:
                break

            combo_list = sorted(combo)
            my_match = set(my_skills) & combo
            new_skills = combo - set(my_skills)

            # Create a theme based on the skill combination
            theme = _generate_project_theme(list(my_match), list(new_skills))
            if theme["name"] in seen_themes:
                continue
            seen_themes.add(theme["name"])

            # Find matching job titles for this combo
            sample_titles = []
            for job in matching_jobs:
                job_skills_lower = {s.lower() for s in job.skills}
                if my_match & job_skills_lower:
                    sample_titles.append(job.title)
                    if len(sample_titles) >= 3:
                        break

            suggestions.append({
                "project_name": theme["name"],
                "description": theme["description"],
                "skills_demonstrated": list(my_match | (new_skills & set(combo_list[:3]))),
                "matching_jobs_count": count,
                "sample_job_titles": sample_titles,
                "estimated_complexity": theme["complexity"],
                "github_repo_idea": theme["repo"],
                "tech_stack": combo_list[:6],
            })

        return json.dumps(suggestions, indent=2)

    finally:
        await db.close()


def _generate_project_theme(
    my_skills: list[str], gap_skills: list[str]
) -> dict:
    """Generate a project theme based on skill overlap and gaps."""
    all_skills = set(s.lower() for s in my_skills + gap_skills)

    # Project templates based on common skill patterns
    templates = [
        {
            "triggers": {"react", "next", "nextjs", "typescript", "tailwind"},
            "name": "Full-Stack Dashboard",
            "description": "Interactive analytics dashboard with real-time data visualization, auth, and responsive design. Demonstrates frontend mastery with modern frameworks.",
            "complexity": "week",
            "repo": "analytics-dashboard",
        },
        {
            "triggers": {"python", "fastapi", "django", "flask", "api"},
            "name": "REST API with Auth & Docs",
            "description": "Production-ready REST API with JWT auth, rate limiting, auto-generated OpenAPI docs, database migrations, and comprehensive tests.",
            "complexity": "week",
            "repo": "production-api-template",
        },
        {
            "triggers": {"python", "ai", "machine learning", "openai", "llm", "gpt"},
            "name": "AI-Powered Tool",
            "description": "SaaS tool that uses LLM APIs for intelligent text processing (summarization, extraction, or classification) with a clean UI and usage tracking.",
            "complexity": "week",
            "repo": "ai-text-toolkit",
        },
        {
            "triggers": {"node", "express", "mongodb", "postgresql", "database"},
            "name": "Multi-tenant SaaS Starter",
            "description": "Backend for a multi-tenant SaaS app with user management, billing stubs, role-based access control, and API documentation.",
            "complexity": "month",
            "repo": "saas-backend-starter",
        },
        {
            "triggers": {"react native", "flutter", "mobile", "ios", "android"},
            "name": "Cross-Platform Mobile App",
            "description": "Mobile app with offline-first architecture, push notifications, and cloud sync. Demonstrates mobile development best practices.",
            "complexity": "month",
            "repo": "mobile-app-starter",
        },
        {
            "triggers": {"automation", "scraping", "selenium", "playwright", "bot"},
            "name": "Web Automation Framework",
            "description": "Extensible web automation tool with anti-detection, scheduling, data extraction, and export capabilities. Shows automation expertise.",
            "complexity": "week",
            "repo": "smart-automation-framework",
        },
        {
            "triggers": {"aws", "cloud", "docker", "kubernetes", "devops", "terraform"},
            "name": "Infrastructure as Code Template",
            "description": "Complete IaC setup with CI/CD pipelines, monitoring, and auto-scaling. Demonstrates DevOps and cloud architecture skills.",
            "complexity": "week",
            "repo": "cloud-infra-template",
        },
    ]

    # Find best matching template
    best_match = None
    best_score = 0

    for template in templates:
        score = len(all_skills & template["triggers"])
        if score > best_score:
            best_score = score
            best_match = template

    if best_match:
        return best_match

    # Generic fallback
    skill_str = ", ".join(my_skills[:3])
    return {
        "name": f"Portfolio Project ({skill_str})",
        "description": f"A showcase project demonstrating {skill_str} skills with clean code, tests, and documentation.",
        "complexity": "week",
        "repo": "portfolio-showcase",
    }
