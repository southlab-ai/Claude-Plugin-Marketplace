"""Pydantic models for Upwork job data."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Job(BaseModel):
    """Complete Upwork job listing with all extracted fields."""

    # Identity
    id: str = Field(description="Upwork job ID (e.g. ~01abc123)")
    url: str
    title: str

    # Description
    description: str = ""

    # Budget / Pricing
    budget_type: str = ""  # "hourly" or "fixed"
    budget_amount: Optional[float] = None
    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    currency: str = "USD"

    # Job Requirements
    experience_level: str = ""  # "Entry", "Intermediate", "Expert"
    duration: str = ""  # e.g. "1 to 3 months"
    weekly_hours: str = ""  # e.g. "Less than 30 hrs/week"
    skills: list[str] = Field(default_factory=list)
    category: str = ""
    subcategory: str = ""

    # Client Info
    client_country: str = ""
    client_city: str = ""
    client_rating: Optional[float] = None
    client_total_spent: Optional[float] = None
    client_hires: Optional[int] = None
    client_active_jobs: Optional[int] = None
    client_jobs_posted: Optional[int] = None
    client_company_size: str = ""
    client_member_since: str = ""
    payment_verified: bool = False

    # Activity
    proposals_count: Optional[int] = None
    interviewing_count: Optional[int] = None
    invites_sent: Optional[int] = None
    connects_required: Optional[int] = None

    # Metadata
    posted_date: str = ""
    source: str = ""  # "best_matches" or "search"
    search_query: str = ""
    fetched_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    raw_html: str = ""


class JobSummary(BaseModel):
    """Lightweight job summary for list responses."""

    id: str
    url: str
    title: str
    budget_type: str = ""
    budget_amount: Optional[float] = None
    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    experience_level: str = ""
    skills: list[str] = Field(default_factory=list)
    client_country: str = ""
    client_rating: Optional[float] = None
    client_total_spent: Optional[float] = None
    proposals_count: Optional[int] = None
    posted_date: str = ""
    source: str = ""

    @classmethod
    def from_job(cls, job: Job) -> JobSummary:
        return cls(**{k: getattr(job, k) for k in cls.model_fields})


class SearchParams(BaseModel):
    """Parameters for an Upwork job search."""

    query: str = ""
    category: str = ""
    experience_level: str = ""  # "entry", "intermediate", "expert"
    job_type: str = ""  # "hourly", "fixed"
    budget_min: int = 0
    budget_max: int = 0
    hourly_rate_min: int = 0
    hourly_rate_max: int = 0
    client_hires: str = ""  # e.g. "1-9", "10+"
    proposals: str = ""  # e.g. "0-4", "5-9"
    hours_per_week: str = ""  # "less_than_30", "more_than_30"
    project_length: str = ""  # "week", "month", "semester", "ongoing"
    sort_by: str = "relevance"
    max_results: int = 20
    page: int = 1

    def to_url_params(self) -> dict[str, str]:
        """Convert search params to Upwork URL query parameters."""
        from ..constants import (
            CATEGORIES,
            EXPERIENCE_LEVELS,
            JOB_TYPES,
            PROJECT_DURATIONS,
            SORT_OPTIONS,
            WORKLOAD_OPTIONS,
        )

        params: dict[str, str] = {}

        if self.query:
            params["q"] = self.query
        if self.sort_by and self.sort_by in SORT_OPTIONS:
            params["sort"] = SORT_OPTIONS[self.sort_by]
        if self.max_results:
            params["per_page"] = str(min(self.max_results, 50))
        if self.page > 1:
            params["page"] = str(self.page)

        # Job type
        if self.job_type and self.job_type in JOB_TYPES:
            params["t"] = JOB_TYPES[self.job_type]

        # Experience level
        if self.experience_level:
            levels = [
                EXPERIENCE_LEVELS[l.strip()]
                for l in self.experience_level.split(",")
                if l.strip() in EXPERIENCE_LEVELS
            ]
            if levels:
                params["contractor_tier"] = ",".join(levels)

        # Budget
        if self.budget_min or self.budget_max:
            low = str(self.budget_min) if self.budget_min else ""
            high = str(self.budget_max) if self.budget_max else ""
            params["amount"] = f"{low}-{high}"

        # Hourly rate
        if self.hourly_rate_min or self.hourly_rate_max:
            low = str(self.hourly_rate_min) if self.hourly_rate_min else ""
            high = str(self.hourly_rate_max) if self.hourly_rate_max else ""
            params["hourly_rate"] = f"{low}-{high}"

        # Category
        if self.category and self.category in CATEGORIES:
            params["category2_uid"] = CATEGORIES[self.category]

        # Client hires
        if self.client_hires:
            params["client_hires"] = self.client_hires

        # Project length
        if self.project_length and self.project_length in PROJECT_DURATIONS:
            params["duration_v3"] = PROJECT_DURATIONS[self.project_length]

        # Hours per week
        if self.hours_per_week and self.hours_per_week in WORKLOAD_OPTIONS:
            params["workload"] = WORKLOAD_OPTIONS[self.hours_per_week]

        return params
