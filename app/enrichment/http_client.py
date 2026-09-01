"""Asynchronous HTTP client for website evidence collection."""

import logging
import time
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class HttpEnrichmentError(Exception):
    """Base exception for HTTP enrichment failures."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpTimeoutError(HttpEnrichmentError):
    """Raised when an HTTP request times out."""

    pass


class HttpBlockedError(HttpEnrichmentError):
    """Raised when access is forbidden or blocked by bot protection (e.g. 403)."""

    pass


class HttpRateLimitedError(HttpEnrichmentError):
    """Raised when request is rate limited (HTTP 429)."""

    pass


class HttpNotFoundError(HttpEnrichmentError):
    """Raised when target page does not exist (HTTP 404)."""

    pass


class HttpInvalidContentError(HttpEnrichmentError):
    """Raised when response is not HTML (e.g. PDF, binary, video)."""

    pass


class HttpOversizedResponseError(HttpEnrichmentError):
    """Raised when response body exceeds maximum allowed size."""

    pass


class EnrichmentHttpClient:
    """Asynchronous HTTP client with connection timeouts, redirects, and size limits."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
        "(CompanyIntelligenceAgent/0.1.0; +https://github.com/company-agent)"
    )

    def __init__(
        self,
        connect_timeout: float = 3.0,
        read_timeout: float = 7.0,
        max_redirects: int = 5,
        max_response_bytes: int = 2_000_000,  # 2 MB limit
        user_agent: Optional[str] = None,
    ) -> None:
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_redirects = max_redirects
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }

    async def fetch_html(self, url: str) -> tuple[int, str, dict[str, str], int]:
        """
        Fetch HTML content from a URL asynchronously.
        Returns tuple of (status_code, html_text, headers, duration_ms).
        """
        start_time = time.monotonic()
        timeout = httpx.Timeout(
            timeout=self.read_timeout + self.connect_timeout,
            connect=self.connect_timeout,
            read=self.read_timeout,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            max_redirects=self.max_redirects,
            follow_redirects=True,
            verify=True,
        ) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # Check status codes
                if response.status_code == 404:
                    raise HttpNotFoundError(f"Page not found (HTTP 404): {url}", status_code=404)
                if response.status_code == 403:
                    raise HttpBlockedError(f"Access forbidden/blocked (HTTP 403): {url}", status_code=403)
                if response.status_code == 429:
                    raise HttpRateLimitedError(f"Rate limited (HTTP 429): {url}", status_code=429)
                if response.status_code >= 500:
                    raise HttpEnrichmentError(
                        f"Server error (HTTP {response.status_code}): {url}",
                        status_code=response.status_code,
                    )
                if response.status_code >= 400:
                    raise HttpEnrichmentError(
                        f"Client error (HTTP {response.status_code}): {url}",
                        status_code=response.status_code,
                    )

                # Check Content-Type header
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(
                    t in content_type for t in ("text/html", "application/xhtml+xml", "text/plain")
                ):
                    raise HttpInvalidContentError(
                        f"Non-HTML content type '{content_type}' at {url}",
                        status_code=response.status_code,
                    )

                # Check Response Size
                content_length = len(response.content)
                if content_length > self.max_response_bytes:
                    raise HttpOversizedResponseError(
                        f"Response size {content_length} bytes exceeds limit of {self.max_response_bytes} bytes",
                        status_code=response.status_code,
                    )

                return response.status_code, response.text, dict(response.headers), duration_ms

            except httpx.TimeoutException as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.warning("HTTP request timed out for %s: %s", url, exc)
                raise HttpTimeoutError(f"Connection/read timeout for {url}") from exc
            except httpx.ConnectError as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.warning("DNS / Connection failed for %s: %s", url, exc)
                raise HttpEnrichmentError(f"Failed to connect to host for {url}: {exc!s}") from exc
            except httpx.HTTPError as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.warning("HTTP error for %s: %s", url, exc)
                raise HttpEnrichmentError(f"HTTP error for {url}: {exc!s}") from exc
