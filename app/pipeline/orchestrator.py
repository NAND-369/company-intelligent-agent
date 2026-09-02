"""Pipeline Orchestrator coordinating ingestion, enrichment, LLM judgment, Google Sheets sync, and telemetry."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    TriggerType,
)
from app.database.models import Company, PipelineRun
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
)
from app.integrations.google_sheets.service import CompanyIngestionService
from app.pipeline.company_processor import CompanyProcessor
from app.pipeline.schemas import (
    PipelineCompanyResult,
    PipelineRunRequest,
    PipelineRunResult,
)
from app.sync.schemas import SyncOutcome
from app.sync.sheets_sync_service import SheetsSyncService

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """End-to-end batch intelligence pipeline orchestrator."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Optional[Settings] = None,
        ingestion_service: Optional[CompanyIngestionService] = None,
        processor: Optional[CompanyProcessor] = None,
        sync_service: Optional[SheetsSyncService] = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ingestion_service = ingestion_service or CompanyIngestionService(session=session, settings=self.settings)
        self.processor = processor or CompanyProcessor(
            session=session,
            enable_browser=self.settings.pipeline_enable_browser,
            browser_timeout_seconds=self.settings.pipeline_browser_timeout_seconds,
            settings=self.settings,
        )
        self.sync_service = sync_service or SheetsSyncService(
            session=session,
            settings=self.settings,
        )

    async def run_pipeline(
        self,
        request: Optional[PipelineRunRequest] = None,
    ) -> PipelineRunResult:
        """
        Execute full intelligence pipeline run:
        Google Sheets Ingestion -> Candidate Discovery -> Concurrency Control -> Enrichment -> LLM -> (Optional) Sheets Sync -> PipelineRun Persistence.
        """
        req = request or PipelineRunRequest()
        start_time = time.monotonic()
        run_id = req.run_id or uuid.uuid4()

        logger.info(
            "Starting pipeline run (run_id=%s, dry_run=%s, skip_ingestion=%s, sync=%s, limit=%s, trigger=%s)",
            run_id,
            req.dry_run,
            req.skip_ingestion,
            req.sync_to_sheets,
            req.limit,
            req.trigger_type,
        )

        try:
            # 1. Initialize or attach PipelineRun record in PostgreSQL if not dry run
            if not req.dry_run:
                if req.run_id:
                    persisted_run = await PipelineRunRepository.get_by_id(self.session, req.run_id)
                    if not persisted_run:
                        persisted_run = await PipelineRunRepository.create(
                            session=self.session,
                            trigger_type=req.trigger_type,
                            status=PipelineRunStatus.RUNNING,
                        )
                        run_id = persisted_run.id
                    else:
                        run_id = persisted_run.id
                else:
                    persisted_run = await PipelineRunRepository.create(
                        session=self.session,
                        trigger_type=req.trigger_type,
                        status=PipelineRunStatus.RUNNING,
                    )
                    run_id = persisted_run.id
                await self.session.commit()

            result = PipelineRunResult(
                run_id=run_id,
                status=PipelineRunStatus.RUNNING,
                trigger_type=req.trigger_type,
                dry_run=req.dry_run,
            )

            # 2. Stage 1: Google Sheets Ingestion (unless skipped)
            if not req.skip_ingestion:
                try:
                    logger.info("Stage 1: Ingesting company rows from Google Sheets...")
                    ingest_res = await self.ingestion_service.ingest_companies()
                    logger.info(
                        "Ingestion complete: read=%d, created=%d, updated=%d, skipped=%d",
                        ingest_res.rows_read,
                        ingest_res.companies_created,
                        ingest_res.companies_updated,
                        ingest_res.rows_skipped,
                    )
                    if ingest_res.errors:
                        result.errors.extend(ingest_res.errors)
                except Exception as exc:
                    msg = f"Ingestion stage error: {exc!s}"
                    logger.warning(msg)
                    result.errors.append(msg)

            # 3. Stage 2: Discover companies needing evaluation
            now = datetime.now(timezone.utc)
            if req.company_ids is not None:
                if len(req.company_ids) == 0:
                    candidates = []
                else:
                    if req.force_reprocess:
                        stmt = (
                            select(Company)
                            .where(Company.id.in_(req.company_ids))
                            .order_by(Company.created_at.asc())
                        )
                    else:
                        stmt = (
                            select(Company)
                            .where(
                                Company.id.in_(req.company_ids),
                                or_(
                                    Company.status.in_([CompanyStatus.PENDING, CompanyStatus.ENRICHED]),
                                    and_(
                                        Company.status == CompanyStatus.PROCESSING,
                                        or_(
                                            Company.lease_expires_at.is_(None),
                                            Company.lease_expires_at < now,
                                        ),
                                    ),
                                ),
                            )
                            .order_by(Company.created_at.asc())
                        )
                    if req.limit:
                        stmt = stmt.limit(req.limit)
                    candidates_res = await self.session.execute(stmt)
                    candidates = list(candidates_res.scalars().all())
            else:
                if req.force_reprocess:
                    stmt = (
                        select(Company)
                        .where(
                            Company.status.in_([
                                CompanyStatus.PENDING,
                                CompanyStatus.ENRICHED,
                                CompanyStatus.JUDGED,
                                CompanyStatus.SYNCED,
                            ])
                        )
                        .order_by(Company.created_at.asc())
                    )
                else:
                    stmt = (
                        select(Company)
                        .where(
                            or_(
                                Company.status.in_([CompanyStatus.PENDING, CompanyStatus.ENRICHED]),
                                and_(
                                    Company.status == CompanyStatus.PROCESSING,
                                    or_(
                                        Company.lease_expires_at.is_(None),
                                        Company.lease_expires_at < now,
                                    ),
                                ),
                            )
                        )
                        .order_by(Company.created_at.asc())
                    )
                if req.limit:
                    stmt = stmt.limit(req.limit)

                candidates_res = await self.session.execute(stmt)
                candidates = list(candidates_res.scalars().all())

            result.companies_discovered = len(candidates)
            candidate_infos = [(c.id, c.name, c.status) for c in candidates]

            logger.info(
                "Stage 2: Discovered %d candidate companies for processing (force_reprocess=%s, scoped_ids=%s).",
                len(candidates),
                req.force_reprocess,
                bool(req.company_ids is not None),
            )

            # 4. Handle Dry Run Preview
            if req.dry_run:
                duration = round(time.monotonic() - start_time, 2)
                result.status = PipelineRunStatus.COMPLETED
                result.duration_seconds = duration
                logger.info("Dry run complete: %d candidate companies identified.", len(candidates))
                return result

            # 5. Stage 3: Process companies with transactional safety and lease tracking
            for co_id, co_name, initial_status in candidate_infos:
                try:
                    has_lease = await CompanyRepository.acquire_lease(
                        session=self.session,
                        company_id=co_id,
                        lease_duration_minutes=self.settings.pipeline_lease_duration_minutes,
                        force=req.force_reprocess,
                    )
                    await self.session.commit()

                    if not has_lease and initial_status != CompanyStatus.PROCESSING:
                        logger.info("Company '%s' is leased by another worker. Skipping.", co_name)
                        continue

                    company = await CompanyRepository.get_by_id(self.session, co_id)
                    if not company:
                        logger.warning("Company '%s' (id=%s) no longer exists. Skipping.", co_name, co_id)
                        continue

                    co_result = await self.processor.process_company(
                        company,
                        force_reprocess=req.force_reprocess,
                    )
                    result.company_results.append(co_result)
                    result.companies_processed += 1

                    if co_result.status in (CompanyStatus.JUDGED, CompanyStatus.SYNCED):
                        result.companies_succeeded += 1
                        if co_result.fit_decision == FitDecision.YES:
                            result.fit_yes_count += 1
                        elif co_result.fit_decision == FitDecision.NO:
                            result.fit_no_count += 1
                        elif co_result.fit_decision == FitDecision.UNCERTAIN:
                            result.fit_uncertain_count += 1

                        # Stage 4 (Optional): Synchronize verdict back to Google Sheets row
                        if req.sync_to_sheets:
                            try:
                                logger.info(
                                    "Synchronizing verdict for '%s' to Google Sheets (force=%s)...",
                                    co_name,
                                    req.force_reprocess,
                                )
                                sync_res = await self.sync_service.sync_company(
                                    company_id=co_id,
                                    force=req.force_reprocess,
                                    dry_run=req.dry_run,
                                )
                                if sync_res.status == SyncOutcome.SUCCESS:
                                    co_result.is_synced = True
                                    co_result.status = CompanyStatus.SYNCED
                                    result.synced_count += 1
                                elif sync_res.error_details:
                                    result.errors.append(f"Sync error for {co_name}: {sync_res.error_details}")
                            except Exception as sync_exc:
                                msg = f"Unexpected sync error for {co_name}: {sync_exc!s}"
                                logger.error(msg)
                                result.errors.append(msg)
                    else:
                        result.companies_failed += 1
                        if co_result.error:
                            result.errors.append(f"Company {co_name}: {co_result.error}")

                except Exception as loop_co_exc:
                    logger.exception("Unexpected error processing company '%s': %s", co_name, loop_co_exc)
                    result.companies_failed += 1
                    result.companies_processed += 1
                    result.errors.append(f"Company {co_name} unhandled error: {loop_co_exc!s}")
                    try:
                        await self.session.rollback()
                        await CompanyRepository.delete(self.session, co_id)
                        await self.session.commit()
                    except Exception as db_err:
                        logger.error("Failed to delete company %s on error: %s", co_name, db_err)
                finally:
                    # Release company lease lock if record still exists
                    try:
                        await CompanyRepository.release_lease(self.session, co_id)
                        await self.session.commit()
                    except Exception as rel_err:
                        logger.debug("Error releasing lease for %s: %s", co_name, rel_err)

                # Update running counters in database
                try:
                    await PipelineRunRepository.update_counters(
                        session=self.session,
                        run_id=run_id,
                        total_companies=result.companies_discovered,
                        processed_count=result.companies_processed,
                        success_count=result.companies_succeeded,
                        synced_count=result.synced_count,
                        fit_yes_count=result.fit_yes_count,
                        fit_no_count=result.fit_no_count,
                        fit_uncertain_count=result.fit_uncertain_count,
                    )
                    await self.session.commit()
                except Exception as counter_err:
                    logger.error("Error updating pipeline run counters: %s", counter_err)

            # 6. Stage 5: Finalize PipelineRun status and metrics
            duration = round(time.monotonic() - start_time, 2)
            result.duration_seconds = duration

            if result.companies_failed == 0:
                terminal_status = PipelineRunStatus.COMPLETED
            elif result.companies_succeeded > 0:
                terminal_status = PipelineRunStatus.PARTIAL_FAILURE
            else:
                terminal_status = PipelineRunStatus.FAILED if result.companies_processed > 0 else PipelineRunStatus.COMPLETED

            result.status = terminal_status

            run_metadata = {
                "errors": result.errors,
                "company_results": [
                    {
                        "company_id": str(r.company_id),
                        "company_name": r.company_name,
                        "website_url": r.website_url,
                        "status": str(r.status),
                        "fit": str(r.fit_decision) if r.fit_decision else None,
                        "confidence": r.confidence,
                        "reasoning": r.reasoning,
                        "follow_up_question": r.follow_up_question,
                        "is_synced": r.is_synced,
                        "error": r.error,
                        "duration_ms": r.duration_ms,
                    }
                    for r in result.company_results
                ],
            }

            await PipelineRunRepository.complete_run(
                session=self.session,
                run_id=run_id,
                status=terminal_status,
                error_summary=run_metadata,
            )
            await self.session.commit()

            logger.info(
                "Pipeline run %s completed with status %s: processed=%d (succeeded=%d, synced=%d, failed=%d) in %.2fs",
                run_id,
                terminal_status,
                result.companies_processed,
                result.companies_succeeded,
                result.synced_count,
                result.companies_failed,
                duration,
            )

            return result

        except Exception as exc:
            logger.exception("Pipeline run %s encountered unhandled exception: %s", run_id, exc)
            if not req.dry_run:
                try:
                    await self.session.rollback()
                    await PipelineRunRepository.complete_run(
                        session=self.session,
                        run_id=run_id,
                        status=PipelineRunStatus.FAILED,
                        error_summary={"fatal_error": str(exc)},
                    )
                    await self.session.commit()
                except Exception as db_exc:
                    logger.exception("Failed to mark pipeline run %s as FAILED: %s", run_id, db_exc)
            raise
