"""SQLite database schema and initialization."""

from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    budget_type TEXT DEFAULT '',
    budget_amount REAL,
    hourly_rate_min REAL,
    hourly_rate_max REAL,
    currency TEXT DEFAULT 'USD',
    experience_level TEXT DEFAULT '',
    duration TEXT DEFAULT '',
    weekly_hours TEXT DEFAULT '',
    skills TEXT DEFAULT '[]',
    category TEXT DEFAULT '',
    subcategory TEXT DEFAULT '',
    client_country TEXT DEFAULT '',
    client_city TEXT DEFAULT '',
    client_rating REAL,
    client_total_spent REAL,
    client_hires INTEGER,
    client_active_jobs INTEGER,
    client_jobs_posted INTEGER,
    client_company_size TEXT DEFAULT '',
    client_member_since TEXT DEFAULT '',
    payment_verified INTEGER DEFAULT 0,
    proposals_count INTEGER,
    interviewing_count INTEGER,
    invites_sent INTEGER,
    connects_required INTEGER,
    posted_date TEXT DEFAULT '',
    source TEXT DEFAULT '',
    search_query TEXT DEFAULT '',
    fetched_at TEXT NOT NULL,
    raw_html TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scrape_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    query TEXT DEFAULT '',
    params TEXT DEFAULT '{}',
    job_count INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_experience ON jobs(experience_level);
"""


async def initialize_db(db: aiosqlite.Connection):
    """Create tables and indexes if they don't exist."""
    await db.executescript(SCHEMA)
    await db.commit()
