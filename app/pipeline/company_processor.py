"""Company processor handling state transitions, enrichment, and LLM evaluation for a single company."""

import asyncio
import logging
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
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
        browser_timeout_seconds: Optional[float] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.http_enrichment_service = http_enrichment_service or HttpEnrichmentService(session=session)
        self.llm_judge_service = llm_judge_service or LLMJudgeService(session=session)
        self.enable_browser = enable_browser
        self.browser_timeout_seconds = (
            browser_timeout_seconds
            if browser_timeout_seconds is not None
            else self.settings.pipeline_browser_timeout_seconds
        )

    async def process_company(
        self,
        company: Company,
        force_reprocess: bool = False,
    ) -> PipelineCompanyResult:
        """
        Execute lifecycle stages for a company:
        1. Check completed work (idempotency/resumability)
        2. HTTP Enrichment (if missing)
        3. Browser Enrichment (if missing and enabled)
        4. LLM Judgment (if missing or force_reprocess)
        """
        start_time = time.monotonic()
        company_id = company.id
        company_name = company.name
        company_url = company.website_url

        logger.info(
            "Processing company '%s' (id=%s, current_status=%s, force=%s)",
            company_name,
            company_id,
            company.status,
            force_reprocess,
        )

        try:
            # 1. Check if company is already evaluated (unless force_reprocess is True)
            if not force_reprocess:
                existing_verdict = await VerdictRepository.get_latest_by_company(self.session, company_id)
                if company.status in (CompanyStatus.JUDGED, CompanyStatus.SYNCED) and existing_verdict is not None:
                    signals = await SignalRepository.list_by_company(self.session, company_id)
                    duration_ms = int((time.monotonic() - start_time) * 1000)
                    logger.info("Company '%s' already evaluated (verdict=%s). Skipping duplicate evaluation.", company_name, existing_verdict.fit)
                    return PipelineCompanyResult(
                        company_id=company_id,
                        company_name=company_name,
                        website_url=company_url,
                        status=company.status,
                        fit_decision=existing_verdict.fit,
                        confidence=existing_verdict.confidence,
                        signals_count=len(signals),
                        duration_ms=duration_ms,
                    )

            # 2. Check existing signals to avoid re-extracting
            existing_signals = await SignalRepository.list_by_company(self.session, company_id)
            has_http_signal = any(s.signal_type == SignalType.HTTP_WEBSITE for s in existing_signals)
            has_browser_signal = any(s.signal_type == SignalType.BROWSER_CAREERS for s in existing_signals)

            # Step A: HTTP website enrichment
            if not has_http_signal:
                logger.info("Executing HTTP enrichment for '%s'", company_name)
                await self.http_enrichment_service.enrich_company(company_id)

            # Step B: Browser careers enrichment with bounded timeout
            if self.enable_browser and not has_browser_signal:
                logger.info(
                    "Executing Browser enrichment for '%s' (timeout=%.1fs)",
                    company_name,
                    self.browser_timeout_seconds,
                )
                try:
                    await asyncio.wait_for(
                        self.http_enrichment_service.enrich_company_with_browser(company_id),
                        timeout=self.browser_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Browser enrichment timed out after %.1fs for '%s' (continuing with static signals)",
                        self.browser_timeout_seconds,
                        company_name,
                    )
                except Exception as b_exc:
                    logger.warning(
                        "Browser enrichment failed for '%s' (continuing with static signals): %s",
                        company_name,
                        b_exc,
                    )

            # Step C: LLM Judge evaluation
            logger.info("Executing LLM evaluation for '%s'", company_name)
            verdict: Optional[Verdict] = await self.llm_judge_service.evaluate_company(company_id)

            # 3. Reload company and signals to capture final state
            updated_company = await CompanyRepository.get_by_id(self.session, company_id)
            final_status = updated_company.status if updated_company else CompanyStatus.JUDGED
            final_signals = await SignalRepository.list_by_company(self.session, company_id)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            fit_decision = verdict.fit if verdict else None
            confidence = verdict.confidence if verdict else None
            reasoning = verdict.reasoning if verdict and isinstance(verdict.reasoning, list) else ([str(verdict.reasoning)] if verdict and verdict.reasoning else [])
            follow_up = verdict.follow_up_question if verdict else None

            return PipelineCompanyResult(
                company_id=company_id,
                company_name=company_name,
                website_url=company_url,
                status=final_status,
                fit_decision=fit_decision,
                confidence=confidence,
                reasoning=reasoning,
                follow_up_question=follow_up,
                signals_count=len(final_signals),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("Error processing company '%s' (id=%s): %s", company_name, company_id, exc)
            try:
                await self.session.rollback()
                # On definitive failure (LLM failure, 429, timeout, malformed JSON, etc.), completely remove the company
                # and all its associated partial signals/verdicts/sync logs so no failed/incomplete records remain in PostgreSQL.
                await CompanyRepository.delete(self.session, company_id)
                await self.session.commit()
                logger.info("Successfully deleted failed company '%s' (id=%s) from PostgreSQL.", company_name, company_id)
            except Exception as db_err:
                logger.error("Failed to delete company %s on error: %s", company_name, db_err)

            return PipelineCompanyResult(
                company_id=company_id,
                company_name=company_name,
                website_url=company_url,
                status=CompanyStatus.FAILED,
                error=str(exc),
                duration_ms=duration_ms,
            )
