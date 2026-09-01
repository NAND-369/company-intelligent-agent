"""BrowserEnricher provider utilizing Playwright for dynamic DOM and careers extraction."""

import logging
import time
from typing import Any, Optional

from app.database.enums import SignalStatus, SignalType
from app.enrichment.browser_client import (
    BrowserClientError,
    PlaywrightBrowserClient,
)
from app.enrichment.browser_extractor import BrowserEvidenceExtractor
from app.enrichment.http_client import HttpEnrichmentError
from app.enrichment.schemas import NormalizedSignalResult

logger = logging.getLogger(__name__)


class BrowserEnricher:
    """Collects factual evidence from dynamic JavaScript-rendered pages using Playwright."""

    def __init__(
        self,
        browser_client: Optional[PlaywrightBrowserClient] = None,
        extractor: Optional[BrowserEvidenceExtractor] = None,
    ) -> None:
        self.browser_client = browser_client or PlaywrightBrowserClient()
        self.extractor = extractor or BrowserEvidenceExtractor()

    async def collect(
        self,
        url: str,
        company_name: str,
        fetch_careers_page: bool = True,
    ) -> NormalizedSignalResult:
        """
        Render website with Playwright headless Chromium and extract dynamic DOM & career facts.
        Returns a structured NormalizedSignalResult with SignalType.BROWSER_CAREERS.
        """
        start_time = time.monotonic()
        logger.info("Starting Playwright browser enrichment for '%s' (%s)", company_name, url)

        try:
            # 1. Render homepage DOM
            status_code, rendered_html, page_title, headers, duration_ms = (
                await self.browser_client.render_page(url)
            )

            # 2. Extract rendered facts from homepage
            homepage_facts, _ = self.extractor.extract_rendered_page(rendered_html, url)

            facts: dict[str, Any] = {
                "company_name_queried": company_name,
                "rendered_page_title": page_title or homepage_facts.page_title,
                "meta_description": homepage_facts.meta_description,
                "og_title": homepage_facts.og_title,
                "og_description": homepage_facts.og_description,
                "headings_summary": homepage_facts.headings,
                "rendered_text_snippet": homepage_facts.main_text_snippet,
                "careers_page_url": homepage_facts.careers_url,
                "discovered_links_count": len(homepage_facts.discovered_links),
                "discovered_links": [l.model_dump() for l in homepage_facts.discovered_links[:10]],
            }

            # 3. Optional shallow dynamic careers page rendering if discovered
            careers_evidence: Optional[dict[str, Any]] = None
            if fetch_careers_page and homepage_facts.careers_url:
                careers_url = homepage_facts.careers_url
                try:
                    logger.info("Rendering discovered careers page with Playwright: %s", careers_url)
                    _, c_html, c_title, _, _ = await self.browser_client.render_page(
                        careers_url,
                        wait_for_selector="#jobs-container, .job-card, .career-card, .job-listing, main",
                    )
                    c_base_facts, c_career_facts = self.extractor.extract_rendered_page(c_html, careers_url)

                    careers_evidence = {
                        "careers_url": careers_url,
                        "careers_page_title": c_title or c_base_facts.page_title,
                        "careers_headings": c_base_facts.headings[:10],
                        "active_jobs_count": c_career_facts["active_jobs_count"],
                        "job_titles": c_career_facts["job_titles"],
                        "hiring_departments": c_career_facts["hiring_departments"],
                        "locations": c_career_facts["locations"],
                        "tech_stack_detected_in_jobs": c_career_facts["tech_stack_detected"],
                        "remote_friendly": c_career_facts["remote_friendly"],
                    }
                except Exception as c_exc:
                    logger.warning("Dynamic careers page rendering failed for %s: %s", careers_url, c_exc)
                    careers_evidence = {
                        "careers_url": careers_url,
                        "render_error": str(c_exc),
                    }

            if careers_evidence:
                facts["careers_evidence"] = careers_evidence

            total_duration = int((time.monotonic() - start_time) * 1000)

            return NormalizedSignalResult(
                signal_type=SignalType.BROWSER_CAREERS,
                status=SignalStatus.SUCCESS,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts=facts,
                raw_data={
                    "http_status": status_code,
                    "rendered_byte_size": len(rendered_html.encode("utf-8", errors="ignore")),
                    "browser_engine": "Playwright Chromium (Headless)",
                },
            )

        except (BrowserClientError, HttpEnrichmentError) as exc:
            total_duration = int((time.monotonic() - start_time) * 1000)
            logger.warning("Browser enrichment failed for '%s' (%s): %s", company_name, url, exc)
            return NormalizedSignalResult(
                signal_type=SignalType.BROWSER_CAREERS,
                status=SignalStatus.FAILED,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts={
                    "company_name_queried": company_name,
                    "error": str(exc),
                },
                error_message=str(exc),
            )

        except Exception as exc:
            total_duration = int((time.monotonic() - start_time) * 1000)
            logger.error("Unexpected error during browser enrichment for '%s' (%s): %s", company_name, url, exc)
            return NormalizedSignalResult(
                signal_type=SignalType.BROWSER_CAREERS,
                status=SignalStatus.FAILED,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts={
                    "company_name_queried": company_name,
                    "error": f"Unexpected browser error: {exc!s}",
                },
                error_message=f"Unexpected browser error: {exc!s}",
            )

    async def close(self) -> None:
        """Clean up underlying browser instance."""
        await self.browser_client.close()
