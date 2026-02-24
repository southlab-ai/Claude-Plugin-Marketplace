"""CAPTCHA detection and handling strategies for Cloudflare and Upwork."""

from __future__ import annotations

import asyncio
import logging
import sys

from playwright.async_api import Page

from ..constants import CLOUDFLARE_INDICATORS

logger = logging.getLogger(__name__)
# MCP servers MUST NOT write to stdout
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def detect_cloudflare(page: Page) -> bool:
    """Check if the current page shows a Cloudflare challenge."""
    try:
        content = await page.content()
        return any(indicator in content for indicator in CLOUDFLARE_INDICATORS)
    except Exception:
        return False


async def wait_for_cloudflare_resolution(page: Page, timeout_ms: int = 30000) -> bool:
    """Wait for a Cloudflare challenge to auto-resolve.

    Returns True if resolved, False if timed out.
    """
    logger.info("Cloudflare challenge detected, waiting for auto-resolution...")
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000)

    while asyncio.get_event_loop().time() < deadline:
        if not await detect_cloudflare(page):
            logger.info("Cloudflare challenge resolved automatically.")
            return True
        await asyncio.sleep(2)

    logger.warning("Cloudflare challenge did not auto-resolve within timeout.")
    return False


async def detect_login_page(page: Page) -> bool:
    """Check if we've been redirected to the login page."""
    url = page.url
    return "/login" in url or "/account-security" in url


async def detect_captcha_element(page: Page) -> str | None:
    """Detect specific CAPTCHA elements on the page.

    Returns the type of CAPTCHA found, or None.
    """
    checks = [
        ("iframe[src*='hcaptcha']", "hcaptcha"),
        ("iframe[src*='recaptcha']", "recaptcha"),
        ("#cf-turnstile", "cloudflare_turnstile"),
        (".cf-challenge", "cloudflare_challenge"),
        ("[data-testid='challenge']", "upwork_challenge"),
    ]
    for selector, captcha_type in checks:
        try:
            element = await page.query_selector(selector)
            if element:
                logger.info(f"Detected CAPTCHA type: {captcha_type}")
                return captcha_type
        except Exception:
            continue
    return None


async def handle_captcha(page: Page, timeout_ms: int = 30000) -> dict:
    """Handle any CAPTCHA on the current page.

    Strategy:
    1. Check for Cloudflare interstitial → wait for auto-resolve
    2. Check for interactive CAPTCHA → return status for human intervention
    3. No CAPTCHA → return success

    Returns:
        dict with keys: resolved (bool), captcha_type (str|None), message (str)
    """
    # Layer 1: Cloudflare interstitial
    if await detect_cloudflare(page):
        resolved = await wait_for_cloudflare_resolution(page, timeout_ms)
        if resolved:
            return {"resolved": True, "captcha_type": "cloudflare", "message": "Auto-resolved."}
        # Didn't auto-resolve, check for interactive element
        captcha_type = await detect_captcha_element(page)
        if captcha_type:
            return {
                "resolved": False,
                "captcha_type": captcha_type,
                "message": f"Interactive {captcha_type} CAPTCHA detected. Please solve it in the browser window.",
            }
        return {
            "resolved": False,
            "captcha_type": "cloudflare",
            "message": "Cloudflare challenge did not resolve. Please check the browser window.",
        }

    # Layer 2: Interactive CAPTCHA (no Cloudflare wrapper)
    captcha_type = await detect_captcha_element(page)
    if captcha_type:
        return {
            "resolved": False,
            "captcha_type": captcha_type,
            "message": f"{captcha_type} CAPTCHA detected. Please solve it in the browser window.",
        }

    # No CAPTCHA
    return {"resolved": True, "captcha_type": None, "message": "No CAPTCHA detected."}
