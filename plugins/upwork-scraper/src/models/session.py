"""Pydantic models for session state."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SessionStatus(BaseModel):
    """Current state of the browser session."""

    is_active: bool = False
    state: str = "not_running"  # not_running, launching, needs_login, active, captcha_required, expired, error
    last_used: Optional[str] = None
    cookie_count: int = 0
    jobs_in_cache: int = 0
    last_scrape_time: Optional[str] = None
    message: str = ""
    error: Optional[str] = None
