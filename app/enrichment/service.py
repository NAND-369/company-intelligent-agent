"""Company enrichment orchestrator service coordinating HTTP and Browser providers."""

import logging
from typing import Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, SignalStatus
from app.database.repositories import CompanyRepository, SignalRepository
from app.enrichment.browser_enricher import BrowserEnricher
from app.enrichment.schemas import HttpEnrichmentResult, NormalizedSignalResult
from app.enrichment.website_enricher import WebsiteEnricher

logger = logging.getLogger(__name__)


class HttpEnrichmentService:
    """Service coordinating website evidence extraction and PostgreSQL signal persistence."""

    def __init__(
        self,
        session: AsyncSession,
        website_enricher: Optional[WebsiteEnricher] = None,
        browser_enricher: Optional[BrowserEnricher] = None,
    ) -> None:
        self.session = session
        self.website_enricher = website_enricher or WebsiteEnricher()
        self.browser_enricher = browser_enricher or BrowserEnricher()

    async def enrich_company(
        self,
        company_id: uuid.UUID,
        fetch_careers_page: bool = True,
    ) -> HttpEnrichmentResult:
        """Enrich a company using fast HTTP extraction and persist Signal in PostgreSQL."""
        return await self._execute_enricher(
            company_id=company_id,
            enricher=self.website_enricher,
            fetch_careers_page=fetch_careers_page,
        )

    async def enrich_company_with_browser(
        self,
        company_id: uuid.UUID,
        fetch_careers_page: bool = True,
    ) -> HttpEnrichmentResult:
        """Enrich a company using Playwright browser automation and persist Signal in PostgreSQL."""
        return await self._execute_enricher(
            company_id=company_id,
            enricher=self.browser_enricher,
            fetch_careers_page=fetch_careers_page,
        )

    async def _execute_enricher(
        self,
        company_id: uuid.UUID,
        enricher: WebsiteEnricher | BrowserEnricher,
        fetch_careers_page: bool = True,
    ) -> HttpEnrichmentResult:
        """Shared execution engine for persisting extracted signals in PostgreSQL."""
        company = await CompanyRepository.get_by_id(self.session, company_id)
        if not company:
            msg = f"Company with ID '{company_id}' not found."
            logger.error(msg)
            return HttpEnrichmentResult(
                company_id=company_id,
                success=False,
                error=msg,
            )

        # 1. Collect signal
        signal_result: NormalizedSignalResult = await enricher.collect(
            url=company.website_url,
            company_name=company.name,
            fetch_careers_page=fetch_careers_page,
        )

        # 2. Persist Signal in PostgreSQL System of Record
        persisted_signal = await SignalRepository.create(
            session=self.session,
            company_id=company.id,
            signal_type=signal_result.signal_type,
            source_url=signal_result.source_url,
            extracted_facts=signal_result.extracted_facts,
            raw_data=signal_result.raw_data,
            status=signal_result.status,
            duration_ms=signal_result.duration_ms,
            error_message=signal_result.error_message,
        )

        # 3. Update company status to ENRICHED if signal was successful
        if signal_result.status == SignalStatus.SUCCESS:
            await CompanyRepository.update_status(
                session=self.session,
                company_id=company.id,
                status=CompanyStatus.ENRICHED,
            )

        await self.session.commit()

        logger.info(
            "Enrichment completed for company %s: Signal id=%s (type=%s, status=%s)",
            company.name,
            persisted_signal.id,
            persisted_signal.signal_type,
            persisted_signal.status,
        )

        return HttpEnrichmentResult(
            company_id=company.id,
            signals_collected=[signal_result],
            success=(signal_result.status == SignalStatus.SUCCESS),
            error=signal_result.error_message,
            total_duration_ms=signal_result.duration_ms,
        )
