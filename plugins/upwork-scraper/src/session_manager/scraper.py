"""HTTP-based scraper that uses transferred browser cookies for fast parallel fetching."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..config import DEFAULT_MAX_JOBS, MAX_CONCURRENT_REQUESTS, REQUEST_DELAY_MS
from ..constants import UPWORK_BASE, UPWORK_BEST_MATCHES_URL, UPWORK_SEARCH_URL
from ..models.job import Job, SearchParams
from .parser import parse_job_detail, parse_job_tiles_from_html

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class UpworkScraper:
    """Scrapes Upwork using HTTP requests with stolen browser session cookies."""

    def __init__(self, cookies: list[dict], user_agent: str):
        self._cookies = {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}
        self._user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def __aenter__(self):
        logger.info(f"[SCRAPER] Initializing httpx client with {len(self._cookies)} cookies")
        logger.info(f"[SCRAPER] Cookie names: {list(self._cookies.keys())[:10]}...")
        self._client = httpx.AsyncClient(
            cookies=self._cookies,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _fetch_page(self, url: str) -> str:
        """Fetch a single page with rate limiting and retry."""
        async with self._semaphore:
            for attempt in range(3):
                try:
                    response = await self._client.get(url)
                    logger.info(
                        f"[SCRAPER] _fetch_page: status={response.status_code}, "
                        f"url={response.url}, size={len(response.text)} chars "
                        f"(attempt {attempt + 1})"
                    )

                    # Check for login redirect (session expired)
                    if response.status_code == 302 or "/login" in str(response.url):
                        logger.warning(f"[SCRAPER] Redirected to login! URL: {response.url}")
                        raise RuntimeError("Session expired - redirected to login.")

                    response.raise_for_status()
                    await asyncio.sleep(REQUEST_DELAY_MS / 1000)
                    return response.text

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        wait = (attempt + 1) * 5
                        logger.warning(f"Rate limited (429), waiting {wait}s...")
                        await asyncio.sleep(wait)
                    elif e.response.status_code >= 500:
                        logger.warning(f"Server error {e.response.status_code}, retrying...")
                        await asyncio.sleep(2)
                    else:
                        logger.error(f"[SCRAPER] HTTP {e.response.status_code} for {url}")
                        raise
                except httpx.ConnectError as e:
                    logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                    await asyncio.sleep(2)

        raise RuntimeError(f"Failed to fetch {url} after 3 attempts.")

    async def fetch_best_matches(
        self, max_jobs: int = DEFAULT_MAX_JOBS, browser_html: Optional[str] = None
    ) -> list[Job]:
        """Fetch Best Matches jobs.

        Best Matches uses dynamic loading, so we need either:
        - browser_html: Pre-rendered HTML from the browser (with scrolling)
        - Or we try HTTP fetch (may get limited results without JS rendering)

        Args:
            max_jobs: Maximum number of jobs to fetch details for.
            browser_html: Optional pre-rendered HTML from browser scrolling.

        Returns:
            List of fully detailed Job objects.
        """
        if browser_html:
            html = browser_html
        else:
            logger.info("Fetching Best Matches via HTTP (limited without JS)...")
            html = await self._fetch_page(UPWORK_BEST_MATCHES_URL)

        # Extract job URLs from the list page
        tiles = parse_job_tiles_from_html(html, source="best_matches")
        logger.info(f"Found {len(tiles)} job tiles on Best Matches page.")

        # Limit the number of jobs to fetch details for
        tiles = tiles[:max_jobs]

        # Fetch full details for each job in parallel
        jobs = await self._fetch_job_details_batch([t["url"] for t in tiles], source="best_matches")
        return jobs

    async def search_jobs(self, params: SearchParams) -> list[Job]:
        """Search for jobs with the given parameters.

        Args:
            params: Search parameters.

        Returns:
            List of fully detailed Job objects.
        """
        url_params = params.to_url_params()
        search_url = f"{UPWORK_SEARCH_URL}?{urlencode(url_params)}"
        logger.info(f"Searching: {search_url}")

        html = await self._fetch_page(search_url)
        tiles = parse_job_tiles_from_html(html, source="search")
        logger.info(f"Found {len(tiles)} job tiles in search results.")

        tiles = tiles[: params.max_results]

        # Fetch full details
        jobs = await self._fetch_job_details_batch(
            [t["url"] for t in tiles],
            source="search",
            search_query=params.query,
        )
        return jobs

    async def fetch_job_detail(self, job_url: str, source: str = "") -> Job:
        """Fetch complete details for a single job.

        Args:
            job_url: Full URL or job ID (with ~prefix).

        Returns:
            Fully detailed Job object.
        """
        if job_url.startswith("~"):
            job_url = f"{UPWORK_BASE}/jobs/{job_url}"

        html = await self._fetch_page(job_url)
        job = parse_job_detail(html, job_url)
        if source:
            job.source = source
        return job

    async def _fetch_job_details_batch(
        self,
        urls: list[str],
        source: str = "",
        search_query: str = "",
    ) -> list[Job]:
        """Fetch full details for multiple jobs concurrently."""
        if not urls:
            return []

        logger.info(f"Fetching details for {len(urls)} jobs...")

        async def _fetch_one(url: str) -> Optional[Job]:
            try:
                job = await self.fetch_job_detail(url, source)
                if search_query:
                    job.search_query = search_query
                return job
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                return None

        tasks = [_fetch_one(url) for url in urls]
        results = await asyncio.gather(*tasks)

        jobs = [j for j in results if j is not None]
        logger.info(f"Successfully fetched {len(jobs)}/{len(urls)} job details.")
        return jobs
