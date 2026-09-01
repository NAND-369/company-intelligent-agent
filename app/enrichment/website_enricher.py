"""WebsiteEnricher provider for fast static HTTP and HTML evidence extraction."""

import logging
import time
from typing import Any, Optional

from app.database.enums import SignalStatus, SignalType
from app.enrichment.extractor import HtmlEvidenceExtractor
from app.enrichment.http_client import (
    EnrichmentHttpClient,
    HttpEnrichmentError,
)
from app.enrichment.schemas import NormalizedSignalResult

logger = logging.getLogger(__name__)


class WebsiteEnricher:
    """Collects factual evidence from a company's website homepage and discovered careers page."""

    def __init__(
        self,
        http_client: Optional[EnrichmentHttpClient] = None,
        extractor: Optional[HtmlEvidenceExtractor] = None,
    ) -> None:
        self.http_client = http_client or EnrichmentHttpClient()
        self.extractor = extractor or HtmlEvidenceExtractor()

    async def collect(
        self,
        url: str,
        company_name: str,
        fetch_careers_page: bool = True,
    ) -> NormalizedSignalResult:
        """
        Extract factual business and career evidence from the company's website.
        Handles errors gracefully and returns a structured NormalizedSignalResult.
        """
        start_time = time.monotonic()
        logger.info("Starting HTTP website enrichment for '%s' (%s)", company_name, url)

        try:
            # 1. Fetch homepage HTML
            status_code, html_text, headers, duration_ms = await self.http_client.fetch_html(url)
            
            # 2. Extract homepage evidence facts
            homepage_facts = self.extractor.extract(html_text, url)

            facts: dict[str, Any] = {
                "company_name_queried": company_name,
                "page_title": homepage_facts.page_title,
                "meta_description": homepage_facts.meta_description,
                "og_title": homepage_facts.og_title,
                "og_description": homepage_facts.og_description,
                "headings_summary": homepage_facts.headings,
                "main_content_snippet": homepage_facts.main_text_snippet,
                "careers_page_url": homepage_facts.careers_url,
                "discovered_links_count": len(homepage_facts.discovered_links),
                "discovered_links": [l.model_dump() for l in homepage_facts.discovered_links[:10]],
            }

            # 3. Optional shallow careers page fetch if discovered
            careers_evidence: Optional[dict[str, Any]] = None
            if fetch_careers_page and homepage_facts.careers_url:
                careers_url = homepage_facts.careers_url
                try:
                    logger.info("Shallow fetch for discovered careers page: %s", careers_url)
                    c_status, c_html, _, _ = await self.http_client.fetch_html(careers_url)
                    careers_facts = self.extractor.extract(c_html, careers_url)
                    careers_evidence = {
                        "careers_url": careers_url,
                        "careers_page_title": careers_facts.page_title,
                        "careers_headings": careers_facts.headings[:10],
                        "careers_snippet": careers_facts.main_text_snippet[:1000],
                        "job_links_found": [
                            l.model_dump()
                            for l in careers_facts.discovered_links
                            if l.category == "careers"
                        ][:10],
                    }
                except Exception as c_exc:
                    logger.warning("Shallow careers page fetch failed for %s: %s", careers_url, c_exc)
                    careers_evidence = {
                        "careers_url": careers_url,
                        "fetch_error": str(c_exc),
                    }

            if careers_evidence:
                facts["careers_evidence"] = careers_evidence

            total_duration = int((time.monotonic() - start_time) * 1000)

            return NormalizedSignalResult(
                signal_type=SignalType.HTTP_WEBSITE,
                status=SignalStatus.SUCCESS,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts=facts,
                raw_data={
                    "http_status": status_code,
                    "homepage_byte_size": homepage_facts.raw_size_bytes,
                    "content_type": headers.get("content-type"),
                    "server": headers.get("server"),
                },
            )

        except HttpEnrichmentError as exc:
            total_duration = int((time.monotonic() - start_time) * 1000)
            logger.warning("HTTP enrichment failed for '%s' (%s): %s", company_name, url, exc)
            return NormalizedSignalResult(
                signal_type=SignalType.HTTP_WEBSITE,
                status=SignalStatus.FAILED,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts={
                    "company_name_queried": company_name,
                    "error": str(exc),
                    "http_status": exc.status_code,
                },
                error_message=str(exc),
            )

        except Exception as exc:
            total_duration = int((time.monotonic() - start_time) * 1000)
            logger.error("Unexpected error during HTTP enrichment for '%s' (%s): %s", company_name, url, exc)
            return NormalizedSignalResult(
                signal_type=SignalType.HTTP_WEBSITE,
                status=SignalStatus.FAILED,
                source_url=url,
                duration_ms=total_duration,
                extracted_facts={
                    "company_name_queried": company_name,
                    "error": f"Unexpected error: {exc!s}",
                },
                error_message=f"Unexpected error: {exc!s}",
            )
