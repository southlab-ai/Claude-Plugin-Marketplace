"""Camoufox browser automation: launch, login, session management."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import BrowserContext, Page

from ..config import BROWSER_HEADLESS, BROWSER_PROFILE_DIR, BROWSER_TIMEOUT
from ..constants import (
    LOGIN_ERROR_MESSAGES,
    SELECTORS,
    UPWORK_BASE,
    UPWORK_BEST_MATCHES_URL,
    UPWORK_LOGIN_URL,
)
from .captcha import detect_login_page, handle_captcha

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class BrowserSession:
    """Manages a Camoufox browser session for Upwork scraping."""

    def __init__(self):
        self._camoufox = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cookies: list[dict] = []
        self._user_agent: str = ""
        self._is_authenticated: bool = False

    @property
    def is_running(self) -> bool:
        return self._page is not None

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @property
    def cookies(self) -> list[dict]:
        return self._cookies

    @property
    def user_agent(self) -> str:
        return self._user_agent

    async def start(self, headless: Optional[bool] = None) -> dict:
        """Launch the Camoufox browser and attempt to restore a session.

        Returns:
            dict with keys: state, message
            state: "active" | "needs_login" | "captcha_required" | "error"
        """
        if self.is_running:
            return {"state": "active", "message": "Browser already running."}

        use_headless = headless if headless is not None else BROWSER_HEADLESS

        try:
            logger.info(f"Launching Camoufox (headless={use_headless})...")

            self._camoufox = AsyncCamoufox(
                headless=use_headless,
                humanize=True,
                geoip=True,
                i_know_what_im_doing=True,
                config={"forceScopeAccess": True},
                disable_coop=True,
            )
            self._browser = await self._camoufox.__aenter__()

            # Create persistent context with saved profile
            self._context = await self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=None,  # Let Camoufox handle fingerprinting
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(BROWSER_TIMEOUT)

            # Try to load Upwork and check if we have a valid session
            logger.info("Navigating to Upwork Best Matches...")
            try:
                await self._page.goto(
                    UPWORK_BEST_MATCHES_URL,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT,
                )
            except Exception as e:
                logger.warning(f"Navigation timeout, trying with longer wait: {e}")
                await self._page.goto(
                    UPWORK_BEST_MATCHES_URL,
                    wait_until="commit",
                    timeout=BROWSER_TIMEOUT * 2,
                )

            # Log where we actually ended up (catches silent redirects)
            logger.info(f"[DEBUG] After navigation, URL: {self._page.url}")
            try:
                title = await self._page.title()
                logger.info(f"[DEBUG] Page title: '{title}'")
            except Exception:
                logger.warning("[DEBUG] Could not read page title")

            # Handle potential CAPTCHA
            captcha_result = await handle_captcha(self._page)
            if not captcha_result["resolved"]:
                return {
                    "state": "captcha_required",
                    "message": captcha_result["message"],
                }

            # Check if redirected to login
            if await detect_login_page(self._page):
                logger.info(f"No valid session, login required. Current URL: {self._page.url}")
                return {
                    "state": "needs_login",
                    "message": "Browser is open. Please log in to Upwork in the browser window and tell me when done.",
                }

            # Session is valid
            await self._extract_session_data()
            self._is_authenticated = True
            logger.info("Session restored successfully.")
            return {"state": "active", "message": "Session active with saved cookies."}

        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            await self.stop()
            return {"state": "error", "message": f"Failed to start browser: {e}"}

    async def check_auth(self) -> dict:
        """Verify the current page is authenticated.

        Call this after the user says they've logged in.
        """
        if not self.is_running:
            return {"state": "not_running", "message": "Browser is not running."}

        try:
            # Refresh the page to check current state
            current_url = self._page.url

            # If on login page, user hasn't logged in yet
            if await detect_login_page(self._page):
                return {
                    "state": "needs_login",
                    "message": "Still on login page. Please complete the login.",
                }

            # Check for CAPTCHA
            captcha_result = await handle_captcha(self._page)
            if not captcha_result["resolved"]:
                return {
                    "state": "captcha_required",
                    "message": captcha_result["message"],
                }

            # If we're on an Upwork page that's not login, we're authenticated
            if UPWORK_BASE in current_url and "/login" not in current_url:
                await self._extract_session_data()
                self._is_authenticated = True
                logger.info("Authentication confirmed.")
                return {"state": "active", "message": "Successfully authenticated."}

            return {"state": "needs_login", "message": "Authentication not confirmed."}

        except Exception as e:
            logger.error(f"Error checking auth: {e}")
            return {"state": "error", "message": f"Error checking auth: {e}"}

    async def _extract_session_data(self):
        """Extract cookies and user-agent from the browser context."""
        try:
            self._cookies = await self._context.cookies()
            self._user_agent = await self._page.evaluate("() => navigator.userAgent")
            logger.info(
                f"Extracted {len(self._cookies)} cookies, "
                f"UA: {self._user_agent[:60]}..."
            )
        except Exception as e:
            logger.warning(f"Failed to extract session data: {e}")
            self._user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )

    async def get_page_html(self, url: str, wait_selector: str = "body") -> str:
        """Navigate to a URL and return the page HTML.

        Used for pages that need browser rendering (Best Matches, etc.).
        """
        if not self.is_running:
            raise RuntimeError("Browser is not running.")

        logger.info(f"[DEBUG] get_page_html: navigating to {url}")
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
        except Exception:
            logger.warning("[DEBUG] domcontentloaded timed out, retrying with commit...")
            await self._page.goto(url, wait_until="commit", timeout=BROWSER_TIMEOUT * 2)

        logger.info(f"[DEBUG] Landed on URL: {self._page.url}")
        try:
            title = await self._page.title()
            logger.info(f"[DEBUG] Page title: '{title}'")
        except Exception:
            pass

        # Handle CAPTCHA if it appears
        captcha_result = await handle_captcha(self._page)
        if not captcha_result["resolved"]:
            raise RuntimeError(captcha_result["message"])

        # Check for login redirect
        if await detect_login_page(self._page):
            self._is_authenticated = False
            raise RuntimeError("Session expired. Please re-authenticate.")

        # Wait for content
        try:
            await self._page.wait_for_selector(wait_selector, timeout=10000)
        except Exception:
            logger.warning(f"[DEBUG] Selector '{wait_selector}' not found within 10s, proceeding anyway")

        html = await self._page.content()
        logger.info(f"[DEBUG] get_page_html: got {len(html)} chars of HTML")
        return html

    async def scroll_and_collect(self, max_scrolls: int = 10) -> str:
        """Scroll the current page to load dynamic content (Best Matches).

        Returns the full page HTML after scrolling.
        """
        if not self.is_running:
            raise RuntimeError("Browser is not running.")

        logger.info(f"[DEBUG] scroll_and_collect: starting (max_scrolls={max_scrolls})")
        for i in range(max_scrolls):
            prev_height = await self._page.evaluate("document.body.scrollHeight")
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)  # Wait for content to load
            new_height = await self._page.evaluate("document.body.scrollHeight")
            logger.info(f"[DEBUG] Scroll {i + 1}: height {prev_height} -> {new_height}")
            if new_height == prev_height:
                logger.info(f"Reached end of content after {i + 1} scrolls.")
                break

        html = await self._page.content()
        logger.info(f"[DEBUG] scroll_and_collect: final HTML size = {len(html)} chars")
        return html

    async def stop(self):
        """Gracefully close the browser and save state."""
        logger.info("Stopping browser session...")
        self._is_authenticated = False

        try:
            if self._context:
                # Extract final cookies before closing
                try:
                    self._cookies = await self._context.cookies()
                except Exception:
                    pass
                await self._context.close()
        except Exception as e:
            logger.warning(f"Error closing context: {e}")
        finally:
            self._context = None
            self._page = None

        try:
            if self._camoufox:
                await self._camoufox.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing camoufox: {e}")
        finally:
            self._camoufox = None
            self._browser = None

        logger.info("Browser session stopped.")
