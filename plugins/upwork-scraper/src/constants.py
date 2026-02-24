"""Upwork URLs, CSS selectors, category UIDs, and field mappings."""

# ── URLs ─────────────────────────────────────────────────────────────────────

UPWORK_BASE = "https://www.upwork.com"
UPWORK_LOGIN_URL = f"{UPWORK_BASE}/ab/account-security/login"
UPWORK_BEST_MATCHES_URL = f"{UPWORK_BASE}/nx/find-work/best-matches"
UPWORK_SEARCH_URL = f"{UPWORK_BASE}/nx/search/jobs/"
UPWORK_JOB_DETAIL_URL = f"{UPWORK_BASE}/jobs/~"  # append job_id

# ── Search URL Parameters ────────────────────────────────────────────────────

SORT_OPTIONS = {
    "relevance": "relevance+desc",
    "recency": "recency",
    "client_spending": "client_total_charge+desc",
    "client_rating": "client_rating+desc",
}

EXPERIENCE_LEVELS = {
    "entry": "1",
    "intermediate": "2",
    "expert": "3",
}

JOB_TYPES = {
    "hourly": "0",
    "fixed": "1",
}

PROJECT_DURATIONS = {
    "week": "week",
    "month": "month",
    "semester": "semester",
    "ongoing": "ongoing",
}

WORKLOAD_OPTIONS = {
    "less_than_30": "as_needed",
    "more_than_30": "full_time",
}

# ── Category UIDs ────────────────────────────────────────────────────────────

CATEGORIES = {
    "Web, Mobile & Software Dev": "531770282580668418",
    "IT & Networking": "531770282580668419",
    "Data Science & Analytics": "531770282580668420",
    "Design & Creative": "531770282580668421",
    "Sales & Marketing": "531770282580668422",
    "Writing": "531770282580668423",
    "Translation": "531770282580668424",
    "Admin Support": "531770282580668425",
    "Customer Service": "531770282580668426",
    "Accounting & Consulting": "531770282580668427",
    "Legal": "531770282580668428",
    "Engineering & Architecture": "531770282584862722",
}

SUBCATEGORIES = {
    "Web Development": "531770282584862733",
    "Mobile Development": "531770282584862734",
    "Software Development": "531770282584862735",
    "Ecommerce Development": "531770282584862737",
    "Desktop Software Development": "531770282584862738",
    "Game Development": "531770282584862736",
    "AI & Machine Learning": "531770282584862740",
    "Data Analysis & Visualization": "531770282584862741",
    "Data Entry": "531770282584862742",
    "Data Mining & Management": "531770282584862743",
}

# ── CSS Selectors ────────────────────────────────────────────────────────────

SELECTORS = {
    # Login page
    "login_username": "#login_username",
    "login_password": "#login_password",

    # Best Matches page
    "job_tile": "article.job-tile",
    "job_title": '[data-test="job-tile-title"] a',
    "job_title_link": '[data-test="job-tile-title"] a',

    # Job detail page
    "detail_title": '[data-test="job-title"]',
    "detail_description": '[data-test="Description"]',
    "detail_budget": '[data-test="job-budget"]',
    "detail_skills": '[data-test="TokenClamp"] .air3-token',
    "detail_experience": '[data-test="experience-level"]',
    "detail_duration": '[data-test="duration"]',
    "detail_workload": '[data-test="workload"]',
    "detail_client_location": '[data-qa="client-location"]',
    "detail_client_spend": '[data-qa="client-spend"]',
    "detail_client_hires": '[data-qa="client-hires"]',
    "detail_client_rating": '[data-qa="client-rating"]',
    "detail_proposals": '[data-test="proposals"]',
    "detail_connects": '[data-test="connects"]',
    "detail_posted": '[data-test="posted-on"]',

    # Search results page
    "search_job_tile": 'article[data-test="JobTile"]',
    "search_next_page": '[data-test="pagination-next"]',
}

# ── Login Selectors ──────────────────────────────────────────────────────────

LOGIN_ERROR_MESSAGES = [
    "Verification failed",
    "Please fix the errors below",
    "Due to technical difficulties",
    "Oops! Something went wrong",
]

# ── Cloudflare Detection ─────────────────────────────────────────────────────

CLOUDFLARE_INDICATORS = [
    "Just a moment...",
    "Checking your browser",
    "cf-challenge",
    "challenge-platform",
    "turnstile",
]
