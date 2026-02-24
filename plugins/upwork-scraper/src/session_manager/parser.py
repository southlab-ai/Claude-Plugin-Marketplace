"""Parse Upwork HTML pages to extract job data.

Handles three page types:
1. Best Matches feed
2. Search results
3. Individual job detail pages

Extraction strategy:
1. Try __NUXT_DATA__ script tag (most reliable, structured data)
2. Fall back to HTML selectors (data-test, data-qa attributes)
3. Fall back to meta tags and generic parsing
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ..constants import SELECTORS, UPWORK_BASE
from ..models.job import Job

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ── Utility Functions ────────────────────────────────────────────────────────


def _clean_text(text: str | None) -> str:
    """Strip whitespace and normalize text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _parse_money(text: str) -> Optional[float]:
    """Extract a numeric dollar amount from text like '$1,500.00'."""
    if not text:
        return None
    match = re.search(r"[\$]?([\d,]+(?:\.\d{2})?)", text.replace(",", ""))
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _parse_int(text: str) -> Optional[int]:
    """Extract an integer from text like '15 proposals' or '5-10'."""
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_job_id_from_url(url: str) -> str:
    """Extract job ID like ~01abc123 from a URL."""
    match = re.search(r"(~[0-9a-f]+)", url)
    return match.group(1) if match else ""


# ── NUXT Data Parser ────────────────────────────────────────────────────────


def _parse_nuxt_data(html: str) -> Optional[list]:
    """Extract and parse the __NUXT_DATA__ script tag.

    Upwork uses Nuxt.js which serializes page data as a flat array
    with index references. Values like "city":141 mean "look up
    index 141 in the data array."
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try the standard NUXT data tag
    script = soup.find("script", id="__NUXT_DATA__")
    if script and script.string:
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            logger.warning("Failed to parse __NUXT_DATA__ JSON.")

    # Try window.__NUXT__ or window.__INITIAL_STATE__
    for script_tag in soup.find_all("script"):
        if not script_tag.string:
            continue
        text = script_tag.string
        for pattern in [
            r"window\.__NUXT__\s*=\s*({.*?});",
            r"window\.__INITIAL_STATE__\s*=\s*({.*?});",
        ]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return [json.loads(match.group(1))]
                except json.JSONDecodeError:
                    continue

    return None


def _resolve_nuxt_value(data: list, index: int) -> Any:
    """Resolve a Nuxt index reference to its actual value."""
    if not isinstance(index, int) or index < 0 or index >= len(data):
        return index  # Return as-is if not a valid index
    value = data[index]
    if isinstance(value, int) and value != index and 0 <= value < len(data):
        # Might be another reference, but avoid infinite recursion
        return data[value]
    return value


# ── Job Tile Parsers (Best Matches & Search Results) ────────────────────────


def parse_job_tiles_from_html(html: str, source: str = "best_matches") -> list[dict]:
    """Extract job URLs and basic info from a list page (Best Matches or Search).

    Returns a list of dicts with minimal info (id, url, title).
    Full details are fetched separately via get_job_details.
    """
    logger.info(f"[PARSER] parse_job_tiles: source={source}, html_size={len(html)} chars")
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Log page identity for debugging
    title_tag = soup.find("title")
    page_title = title_tag.get_text() if title_tag else "(no <title>)"
    logger.info(f"[PARSER] Page <title>: '{page_title}'")

    # Log body text preview to detect Cloudflare/error/empty pages
    body = soup.find("body")
    if body:
        body_text = _clean_text(body.get_text())[:300]
        logger.info(f"[PARSER] Body text preview: {body_text}")
    else:
        logger.warning("[PARSER] No <body> tag in HTML!")

    # Try multiple selector strategies for job tiles
    tile_selectors = [
        '[data-test="job-tile-list"] > section',  # Current Upwork (2025+): sections inside job-tile-list
        "article.job-tile",
        'article[data-test="JobTile"]',
        'div[data-test="job-tile-list"] article',
        "section.air3-card-section",  # Current Upwork card style
        "section.up-card-section",
        'div[class*="job-tile"]',
    ]

    tiles = []
    for selector in tile_selectors:
        tiles = soup.select(selector)
        if tiles:
            logger.info(f"[PARSER] Found {len(tiles)} tiles with selector: {selector}")
            break

    if not tiles:
        # Log what data-test attributes ARE on the page (helps discover new selectors)
        logger.warning("[PARSER] No tiles matched any known selector.")
        data_test_els = soup.find_all(attrs={"data-test": True})
        data_test_values = sorted(set(el["data-test"] for el in data_test_els[:50]))
        if data_test_values:
            logger.info(f"[PARSER] data-test attrs on page: {data_test_values}")
        else:
            logger.warning("[PARSER] No data-test attributes found — page may not be Upwork content")

        # Last resort: look for any links to job detail pages
        # URL format: /jobs/Title_~0ID/ or /jobs/~0ID or /details/~0ID
        links = soup.find_all("a", href=re.compile(r"/jobs/.*~|/details/.*~"))
        logger.info(f"[PARSER] Fallback: found {len(links)} links to job pages")
        seen = set()
        for link in links:
            href = link.get("href", "")
            job_id = _extract_job_id_from_url(href)
            if job_id and job_id not in seen:
                seen.add(job_id)
                url = urljoin(UPWORK_BASE, href)
                jobs.append({
                    "id": job_id,
                    "url": url,
                    "title": _clean_text(link.get_text()),
                    "source": source,
                })
        logger.info(f"[PARSER] Fallback extracted {len(jobs)} unique jobs from links")
        return jobs

    for tile in tiles:
        job_data = _parse_single_tile(tile, source)
        if job_data:
            jobs.append(job_data)

    return jobs


def _parse_single_tile(tile: Tag, source: str) -> Optional[dict]:
    """Parse a single job tile element into a dict."""
    # Find the title link
    title_link = None
    for selector in [
        '[data-test="job-tile-title"] a',
        '[data-test="UpLink"] ',
        "h2 a",
        "h3 a",
        'a[href*="/jobs/"][href*="~"]',  # Matches /jobs/Title_~0ID/ and /jobs/~0ID
        'a[href*="/details/"][href*="~"]',
    ]:
        title_link = tile.select_one(selector)
        if title_link:
            break

    if not title_link:
        return None

    href = title_link.get("href", "")
    job_id = _extract_job_id_from_url(href)
    if not job_id:
        return None

    url = urljoin(UPWORK_BASE, href)
    title = _clean_text(title_link.get_text())

    # Extract additional info from tile if available
    data = {
        "id": job_id,
        "url": url,
        "title": title,
        "source": source,
    }

    # Try to get description snippet
    desc_el = (
        tile.select_one('[data-test="job-description-text"]')
        or tile.select_one('[data-test="job-description-line-clamp"]')
        or tile.select_one('p[class*="description"]')
    )
    if desc_el:
        data["description"] = _clean_text(desc_el.get_text())

    # Try to get budget / job type (new: data-test="job-type" with "Hourly: $30-$45" or "Fixed: $500")
    budget_el = (
        tile.select_one('[data-test="job-type"]')
        or tile.select_one('[data-test="job-budget"]')
        or tile.select_one('[data-test="budget"]')
        or tile.select_one('span[class*="budget"]')
    )
    if budget_el:
        budget_text = _clean_text(budget_el.get_text())
        data["budget_amount"] = _parse_money(budget_text)
        if "hourly" in budget_text.lower() or "/hr" in budget_text.lower():
            data["budget_type"] = "hourly"
            range_match = re.search(r"\$([\d,.]+)\s*[-–]\s*\$([\d,.]+)", budget_text)
            if range_match:
                data["hourly_rate_min"] = float(range_match.group(1).replace(",", ""))
                data["hourly_rate_max"] = float(range_match.group(2).replace(",", ""))
        elif budget_text:
            data["budget_type"] = "fixed"

    # Try to get skills (new: a[data-test="attr-item"] or .air3-token)
    skill_tags = (
        tile.select('a[data-test="attr-item"]')
        or tile.select('[data-test="token-container"] a')
        or tile.select(".air3-token")
        or tile.select('[data-test="TokenClamp"] .air3-token')
        or tile.select('span[class*="skill"]')
    )
    if skill_tags:
        data["skills"] = [_clean_text(s.get_text()) for s in skill_tags if s.get_text().strip()]

    # Try to get experience level (new: data-test="contractor-tier")
    exp_el = (
        tile.select_one('[data-test="contractor-tier"]')
        or tile.select_one('[data-test="experience-level"]')
    )
    if exp_el:
        data["experience_level"] = _clean_text(exp_el.get_text())

    # Try to get proposals count
    proposals_el = tile.select_one('[data-test="proposals"]')
    if proposals_el:
        data["proposals_count"] = _parse_int(proposals_el.get_text())

    # Try to get posted date
    posted_el = tile.select_one('[data-test="posted-on"]') or tile.select_one("time")
    if posted_el:
        data["posted_date"] = _clean_text(posted_el.get_text()) or posted_el.get("datetime", "")

    return data


# ── Job Detail Page Parser ───────────────────────────────────────────────────


def parse_job_detail(html: str, job_url: str = "") -> Job:
    """Parse a complete job detail page into a Job model.

    Tries NUXT data first, falls back to HTML selectors.
    """
    logger.info(f"[PARSER] parse_job_detail: url={job_url}, html_size={len(html)} chars")
    soup = BeautifulSoup(html, "html.parser")
    job_id = _extract_job_id_from_url(job_url) or ""

    data: dict[str, Any] = {
        "id": job_id,
        "url": job_url,
        "raw_html": html,
    }

    # Strategy 1: Try NUXT data
    nuxt = _parse_nuxt_data(html)
    if nuxt:
        nuxt_data = _extract_from_nuxt(nuxt)
        nuxt_fields = {k: v for k, v in nuxt_data.items() if v}
        data.update(nuxt_fields)
        logger.info(f"[PARSER] NUXT extracted {len(nuxt_fields)} fields: {list(nuxt_fields.keys())}")
    else:
        logger.info("[PARSER] No __NUXT_DATA__ found, skipping NUXT strategy")

    # Strategy 2: HTML selectors (fill in gaps)
    html_data = _extract_from_html(soup)
    html_added = 0
    for key, value in html_data.items():
        if value and not data.get(key):
            data[key] = value
            html_added += 1
    logger.info(f"[PARSER] HTML selectors: found {len(html_data)} fields, added {html_added} new")

    # Strategy 3: Meta tags (last resort)
    meta_data = _extract_from_meta(soup)
    meta_added = 0
    for key, value in meta_data.items():
        if value and not data.get(key):
            data[key] = value
            meta_added += 1
    if meta_added:
        logger.info(f"[PARSER] Meta tags: added {meta_added} fields")

    # Ensure required fields
    if not data.get("title"):
        data["title"] = "Unknown Job"
        logger.warning(f"[PARSER] No title found for {job_url} — all strategies failed")

    final_fields = [k for k, v in data.items() if v and k not in ("raw_html", "id", "url")]
    logger.info(f"[PARSER] Final job '{data.get('title', '?')[:50]}' has fields: {final_fields}")

    return Job(**data)


def _extract_from_nuxt(nuxt_data: list) -> dict[str, Any]:
    """Extract job fields from parsed NUXT data."""
    result: dict[str, Any] = {}

    if not nuxt_data:
        return result

    # If it's a single dict (from window.__NUXT__), search it directly
    if len(nuxt_data) == 1 and isinstance(nuxt_data[0], dict):
        flat = nuxt_data[0]
        _search_dict_for_job_fields(flat, result)
        return result

    # For array-based NUXT data, search through all items
    for i, item in enumerate(nuxt_data):
        if isinstance(item, dict):
            _search_dict_for_job_fields(item, result)
        elif isinstance(item, str):
            # Look for key names that map to job fields
            key_map = {
                "title": "title",
                "description": "description",
                "skills": "skills",
                "duration": "duration",
                "budget": "budget_amount",
                "hourlyBudgetMin": "hourly_rate_min",
                "hourlyBudgetMax": "hourly_rate_max",
                "amount": "budget_amount",
                "contractorTier": "experience_level",
                "publishedOn": "posted_date",
                "clientCountry": "client_country",
            }
            if item in key_map and i + 1 < len(nuxt_data):
                next_val = nuxt_data[i + 1]
                if isinstance(next_val, int) and next_val < len(nuxt_data):
                    result[key_map[item]] = _resolve_nuxt_value(nuxt_data, next_val)
                else:
                    result[key_map[item]] = next_val

    return result


def _search_dict_for_job_fields(d: dict, result: dict):
    """Recursively search a dict for job-related fields."""
    field_map = {
        "title": "title",
        "jobTitle": "title",
        "description": "description",
        "jobDescription": "description",
        "skills": "skills",
        "duration": "duration",
        "durationLabel": "duration",
        "budget": "budget_amount",
        "amount": "budget_amount",
        "hourlyBudgetMin": "hourly_rate_min",
        "hourlyBudgetMax": "hourly_rate_max",
        "contractorTier": "experience_level",
        "tierLabel": "experience_level",
        "publishedOn": "posted_date",
        "createdOn": "posted_date",
        "clientCountry": "client_country",
        "country": "client_country",
        "city": "client_city",
        "totalSpent": "client_total_spent",
        "totalHires": "client_hires",
        "openJobs": "client_active_jobs",
        "postedJobCount": "client_jobs_posted",
        "score": "client_rating",
        "paymentVerificationStatus": "payment_verified",
        "proposalCount": "proposals_count",
        "inviteCount": "invites_sent",
        "interviewCount": "interviewing_count",
        "connectPrice": "connects_required",
        "categoryName": "category",
        "subcategoryName": "subcategory",
    }

    for key, value in d.items():
        if key in field_map and value is not None:
            target = field_map[key]
            if target not in result or not result[target]:
                if target == "payment_verified":
                    result[target] = value == 1 or value == "verified" or value is True
                elif target in ("budget_amount", "hourly_rate_min", "hourly_rate_max", "client_total_spent", "client_rating"):
                    result[target] = _parse_money(str(value)) if isinstance(value, str) else value
                elif target in ("client_hires", "client_active_jobs", "client_jobs_posted", "proposals_count", "invites_sent", "interviewing_count", "connects_required"):
                    result[target] = _parse_int(str(value)) if isinstance(value, str) else value
                elif target == "skills" and isinstance(value, list):
                    result[target] = [
                        s.get("name", s) if isinstance(s, dict) else str(s) for s in value
                    ]
                else:
                    result[target] = value

        # Recurse into nested dicts
        if isinstance(value, dict):
            _search_dict_for_job_fields(value, result)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _search_dict_for_job_fields(item, result)


def _extract_from_html(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract job fields from HTML elements using CSS selectors."""
    result: dict[str, Any] = {}

    # Title
    for sel in ['[data-test="job-title"]', "h1", '[data-test="JobTitle"]']:
        el = soup.select_one(sel)
        if el:
            result["title"] = _clean_text(el.get_text())
            break

    # Description
    for sel in ['[data-test="Description"]', '[data-test="job-description"]', ".job-description"]:
        el = soup.select_one(sel)
        if el:
            result["description"] = _clean_text(el.get_text())
            break

    # Budget
    el = soup.select_one('[data-test="job-budget"]') or soup.select_one('[data-test="Budget"]')
    if el:
        text = _clean_text(el.get_text())
        result["budget_amount"] = _parse_money(text)
        if "/hr" in text.lower():
            result["budget_type"] = "hourly"
            # Try to extract range
            range_match = re.search(r"\$([\d,.]+)\s*[-–]\s*\$([\d,.]+)", text)
            if range_match:
                result["hourly_rate_min"] = float(range_match.group(1).replace(",", ""))
                result["hourly_rate_max"] = float(range_match.group(2).replace(",", ""))
        else:
            result["budget_type"] = "fixed"

    # Skills
    skill_els = soup.select('[data-test="TokenClamp"] .air3-token') or soup.select(
        'a[data-test="attr-item"]'
    )
    if skill_els:
        result["skills"] = [_clean_text(s.get_text()) for s in skill_els if s.get_text().strip()]

    # Experience level
    el = soup.select_one('[data-test="experience-level"]')
    if el:
        result["experience_level"] = _clean_text(el.get_text())

    # Duration
    el = soup.select_one('[data-test="duration"]')
    if el:
        result["duration"] = _clean_text(el.get_text())

    # Workload
    el = soup.select_one('[data-test="workload"]')
    if el:
        result["weekly_hours"] = _clean_text(el.get_text())

    # Client info
    el = soup.select_one('[data-qa="client-location"]')
    if el:
        result["client_country"] = _clean_text(el.get_text())

    el = soup.select_one('[data-qa="client-spend"]')
    if el:
        result["client_total_spent"] = _parse_money(el.get_text())

    el = soup.select_one('[data-qa="client-hires"]')
    if el:
        result["client_hires"] = _parse_int(el.get_text())

    el = soup.select_one('[data-qa="client-rating"]')
    if el:
        rating_text = _clean_text(el.get_text())
        result["client_rating"] = _parse_money(rating_text)

    # Proposals
    el = soup.select_one('[data-test="proposals"]')
    if el:
        result["proposals_count"] = _parse_int(el.get_text())

    # Connects
    el = soup.select_one('[data-test="connects"]')
    if el:
        result["connects_required"] = _parse_int(el.get_text())

    # Posted date
    el = soup.select_one('[data-test="posted-on"]') or soup.select_one("time")
    if el:
        result["posted_date"] = _clean_text(el.get_text()) or el.get("datetime", "")

    return result


def _extract_from_meta(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract job info from meta tags as last resort."""
    result: dict[str, Any] = {}

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result["description"] = meta_desc["content"]

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        result["title"] = og_title["content"]

    og_url = soup.find("meta", attrs={"property": "og:url"})
    if og_url and og_url.get("content"):
        result["url"] = og_url["content"]
        if not result.get("id"):
            result["id"] = _extract_job_id_from_url(og_url["content"])

    return result
