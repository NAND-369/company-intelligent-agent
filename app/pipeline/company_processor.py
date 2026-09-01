"""Company processor handling state transitions, enrichment, and LLM evaluation for a single company."""

import logging
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, SignalType
from app.database.models import Company, Verdict
from app.database.repositories import (
    CompanyRepository,
    SignalRepository,
    VerdictRepository,
)
from app.enrichment.service import HttpEnrichmentService
from app.llm.service import LLMJudgeService
from app.pipeline.schemas import PipelineCompanyResult

logger = logging.getLogger(__name__)


class CompanyProcessor:
    """Processes a single company through the enrichment and LLM evaluation lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        http_enrichment_service: Optional[HttpEnrichmentService] = None,
        llm_judge_service: Optional[LLMJudgeService] = None,
        enable_browser: bool = True,
    ) -> None:
        self.session = session
        self.http_enrichment_service = http_enrichment_service or HttpEnrichmentService(session=session)
        self.llm_judge_service = llm_judge_service or LLMJudgeService(session=session)
        self.enable_browser = enable_browser

    async def process_company(self, company: Company) -> PipelineCompanyResult:
        """
        Execute lifecycle stages for a company:
        1. Check completed work (idempotency/resumability)
        2. HTTP Enrichment (if missing)
        3. Browser Enrichment (if missing and enabled)
        4. LLM Judgment (if missing)
        """
        start_time = time.monotonic()
        logger.info("Processing company '%s' (id=%s, current_status=%s)", company.name, company.id, company.status)

        try:
            # 1. Check if company is already evaluated
            existing_verdict = await VerdictRepository.get_latest_by_company(self.session, company.id)
            if company.status == CompanyStatus.JUDGED and existing_verdict is not None:
                signals = await SignalRepository.list_by_company(self.session, company.id)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.info("Company '%s' already evaluated (verdict=%s). Skipping duplicate evaluation.", company.name, existing_verdict.fit)
                return PipelineCompanyResult(
                    company_id=company.id,
                    company_name=company.name,
                    website_url=company.website_url,
                    status=company.status,
                    fit_decision=existing_verdict.fit,
                    confidence=existing_verdict.confidence,
                    signals_count=len(signals),
                    duration_ms=duration_ms,
                )

            # 2. Check existing signals to avoid re-extracting
            existing_signals = await SignalRepository.list_by_company(self.session, company.id)
            has_http_signal = any(s.signal_type == SignalType.HTTP_WEBSITE for s in existing_signals)
            has_browser_signal = any(s.signal_type == SignalType.BROWSER_CAREERS for s in existing_signals)

            # Step A: HTTP website enrichment
            if not has_http_signal:
                logger.info("Executing HTTP enrichment for '%s'", company.name)
                await self.http_enrichment_service.enrich_company(company.id)

            # Step B: Browser careers enrichment
            if self.enable_browser and not has_browser_signal:
                logger.info("Executing Browser enrichment for '%s'", company.name)
                await self.http_enrichment_service.enrich_company_with_browser(company.id)

            # Step C: LLM Judge evaluation
            logger.info("Executing LLM evaluation for '%s'", company.name)
            verdict: Optional[Verdict] = await self.llm_judge_service.evaluate_company(company.id)

            # 3. Reload company and signals to capture final state
            updated_company = await CompanyRepository.get_by_id(self.session, company.id)
            final_status = updated_company.status if updated_company else CompanyStatus.JUDGED
            final_signals = await SignalRepository.list_by_company(self.session, company.id)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            fit_decision = verdict.fit if verdict else None
            confidence = verdict.confidence if verdict else None

            return PipelineCompanyResult(
                company_id=company.id,
                company_name=company.name,
                website_url=company.website_url,
                status=final_status,
                fit_decision=fit_decision,
                confidence=confidence,
                signals_count=len(final_signals),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Error processing company '%s' (id=%s): %s", company.name, company.id, exc)
            await CompanyRepository.update_status(
                session=self.session,
                company_id=company.id,
                status=CompanyStatus.FAILED,
            )
            await self.session.commit()

            return PipelineCompanyResult(
                company_id=company.id,
                company_name=company.name,
                website_url=company.website_url,
                status=CompanyStatus.FAILED,
                error=str(exc),
                duration_ms=duration_ms,
            )
