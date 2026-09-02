"""Playwright asynchronous browser client for dynamic DOM rendering."""

import asyncio
import logging
import time
from typing import Optional
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.enrichment.http_client import (
    HttpBlockedError,
    HttpEnrichmentError,
    HttpNotFoundError,
    HttpRateLimitedError,
    HttpSecurityError,
    HttpTimeoutError,
)
from app.enrichment.url_validator import validate_target_url

logger = logging.getLogger(__name__)


class BrowserClientError(HttpEnrichmentError):
    """Base exception for Playwright browser execution failures."""

    pass


class BrowserNavigationTimeoutError(HttpTimeoutError):
    """Raised when page navigation or DOM hydration times out in Playwright."""

    pass


class PlaywrightBrowserClient:
    """Managed asynchronous Playwright headless Chromium client."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
        "(CompanyIntelligenceAgent/0.1.0; +https://github.com/company-agent)"
    )

    def __init__(
        self,
        headless: bool = True,
        navigation_timeout_ms: int = 15000,
        hydration_wait_ms: int = 500,
        max_concurrent_browsers: int = 2,
        user_agent: Optional[str] = None,
    ) -> None:
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self.hydration_wait_ms = hydration_wait_ms
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self._semaphore = asyncio.Semaphore(max_concurrent_browsers)

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        """Lazily initialize shared browser instance with thread-safe lock."""
        if self._browser and self._browser.is_connected():
            return self._browser

        async with self._lock:
            if self._browser and self._browser.is_connected():
                return self._browser

            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-zygote",
                    ],
                )
                logger.info("Playwright Chromium browser launched successfully.")
                return self._browser
            except Exception as exc:
                logger.error("Failed to launch Playwright Chromium: %s", exc)
                raise BrowserClientError(f"Playwright browser initialization failed: {exc!s}") from exc

    async def render_page(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
    ) -> tuple[int, str, str, dict[str, str], int]:
        """
        Navigate to a URL with headless Chromium, execute JavaScript, and capture rendered HTML.
        Returns: (status_code, rendered_html, page_title, headers, duration_ms).
        """
        # Enforce SSRF & scheme validation (allow file:// for offline testing fixtures)
        is_valid, err_reason = validate_target_url(url, allow_file_scheme=True)
        if not is_valid:
            logger.warning("Playwright rejected unsafe/invalid URL '%s': %s", url, err_reason)
            raise HttpSecurityError(f"URL validation failed: {err_reason}")

        start_time = time.monotonic()
        browser = await self._ensure_browser()

        async with self._semaphore:
            context: Optional[BrowserContext] = None
            try:
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                page = await context.new_page()
                page.set_default_navigation_timeout(self.navigation_timeout_ms)
                page.set_default_timeout(self.navigation_timeout_ms)

                # Execute bounded navigation
                response = await page.goto(url, wait_until="domcontentloaded")

                # Determine HTTP status code
                status_code = 200
                headers: dict[str, str] = {}
                if response:
                    status_code = response.status
                    headers = response.headers

                if status_code == 404:
                    raise HttpNotFoundError(f"Page not found (HTTP 404): {url}", status_code=404)
                if status_code == 403:
                    raise HttpBlockedError(f"Access blocked (HTTP 403): {url}", status_code=403)
                if status_code == 429:
                    raise HttpRateLimitedError(f"Rate limited (HTTP 429): {url}", status_code=429)

                # Wait for optional selector or short hydration delay
                if wait_for_selector:
                    try:
                        await page.wait_for_selector(wait_for_selector, timeout=3000)
                    except Exception:
                        logger.debug("Selector %s not found within timeout; continuing", wait_for_selector)
                elif self.hydration_wait_ms > 0:
                    await page.wait_for_timeout(self.hydration_wait_ms)

                # Capture final rendered DOM and title
                rendered_html = await page.content()
                page_title = await page.title()
                duration_ms = int((time.monotonic() - start_time) * 1000)

                return status_code, rendered_html, page_title, headers, duration_ms

            except (HttpNotFoundError, HttpBlockedError, HttpRateLimitedError):
                raise
            except Exception as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                err_str = str(exc)
                if "Timeout" in err_str or "timed out" in err_str.lower():
                    logger.warning("Playwright navigation timed out for %s: %s", url, exc)
                    raise BrowserNavigationTimeoutError(f"Browser navigation timed out for {url}") from exc
                logger.warning("Playwright execution error for %s: %s", url, exc)
                raise BrowserClientError(f"Browser rendering failed for {url}: {exc!s}") from exc

            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception as close_err:
                        logger.debug("Error closing browser context: %s", close_err)

    async def close(self) -> None:
        """Close browser instance and stop Playwright cleanly."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.debug("Error closing browser: %s", exc)
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as exc:
                    logger.debug("Error stopping Playwright: %s", exc)
                self._playwright = None
            logger.info("Playwright browser closed and resources cleaned up.")
