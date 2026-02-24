"""Pydantic models for market analysis and portfolio suggestions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillCount(BaseModel):
    skill: str
    count: int
    percentage: float


class BudgetBucket(BaseModel):
    range: str
    count: int
    percentage: float


class MarketAnalysis(BaseModel):
    """Aggregated market requirements from cached jobs."""

    total_jobs_analyzed: int = 0
    skill_focus: str = ""
    top_skills: list[SkillCount] = Field(default_factory=list)
    budget_distribution: list[BudgetBucket] = Field(default_factory=list)
    experience_breakdown: dict[str, int] = Field(default_factory=dict)
    job_type_split: dict[str, int] = Field(default_factory=dict)
    avg_hourly_rate_min: float = 0.0
    avg_hourly_rate_max: float = 0.0
    avg_fixed_budget: float = 0.0
    top_categories: list[SkillCount] = Field(default_factory=list)
    common_requirements: list[str] = Field(default_factory=list)


class PortfolioProject(BaseModel):
    """A suggested portfolio project based on market demand."""

    project_name: str
    description: str
    skills_demonstrated: list[str]
    matching_jobs_count: int
    sample_job_titles: list[str]
    estimated_complexity: str  # "weekend", "week", "month"
    github_repo_idea: str
    tech_stack: list[str] = Field(default_factory=list)
