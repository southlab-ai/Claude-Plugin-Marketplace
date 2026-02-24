"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = DATA_DIR / "upwork_jobs.db"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
LOG_DIR = DATA_DIR / "logs"

# Session manager
SESSION_MANAGER_HOST = os.getenv("SESSION_MANAGER_HOST", "127.0.0.1")
SESSION_MANAGER_PORT = int(os.getenv("SESSION_MANAGER_PORT", "8024"))
SESSION_MANAGER_URL = f"http://{SESSION_MANAGER_HOST}:{SESSION_MANAGER_PORT}"

# Browser
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))

# Scraping
MAX_CONCURRENT_REQUESTS = 10
REQUEST_DELAY_MS = 500
DEFAULT_MAX_JOBS = 20
CACHE_TTL_SECONDS = 3600  # 1 hour


def ensure_dirs():
    """Create required data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
