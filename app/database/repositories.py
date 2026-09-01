"""Data access repository layer for database domain models."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SignalStatus,
    SignalType,
    SyncDirection,
    SyncStatus,
    TriggerType,
)
from app.database.models import Company, PipelineRun, Signal, SyncLog, Verdict


class CompanyRepository:
    """Repository operations for Company entities."""

    @staticmethod
    async def get_by_id(session: AsyncSession, company_id: uuid.UUID) -> Optional[Company]:
        """Find a company by its internal primary key."""
        stmt = select(Company).where(Company.id == company_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_sheet_row_id(session: AsyncSession, sheet_row_id: str) -> Optional[Company]:
        """Find a company by its stable Google Sheet row identifier."""
        stmt = select(Company).where(Company.sheet_row_id == sheet_row_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_with_relations(session: AsyncSession, company_id: uuid.UUID) -> Optional[Company]:
        """Fetch a company with eager-loaded signals, verdicts, and sync logs."""
        stmt = (
            select(Company)
            .where(Company.id == company_id)
            .options(
                selectinload(Company.signals),
                selectinload(Company.verdicts),
                selectinload(Company.sync_logs),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_website(session: AsyncSession, website_url: str) -> Optional[Company]:
        """Find a company by its normalized website URL."""
        stmt = select(Company).where(Company.website_url == website_url)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str,
        website_url: str,
        sheet_row_id: Optional[str] = None,
        domain: Optional[str] = None,
        status: CompanyStatus = CompanyStatus.PENDING,
    ) -> Company:
        """Insert a new company record."""
        company = Company(
            name=name,
            website_url=website_url,
            sheet_row_id=sheet_row_id,
            domain=domain,
            status=status,
        )
        session.add(company)
        await session.flush()
        return company

    @staticmethod
    async def upsert_by_sheet_row_id(
        session: AsyncSession,
        name: str,
        website_url: str,
        sheet_row_id: str,
        domain: Optional[str] = None,
    ) -> tuple[Company, bool]:
        """
        Idempotently find or create a company by sheet_row_id.
        Returns a tuple of (Company, created: bool).
        """
        existing = await CompanyRepository.get_by_sheet_row_id(session, sheet_row_id)
        if existing:
            existing.name = name
            existing.website_url = website_url
            if domain:
                existing.domain = domain
            await session.flush()
            return existing, False

        new_company = await CompanyRepository.create(
            session=session,
            name=name,
            website_url=website_url,
            sheet_row_id=sheet_row_id,
            domain=domain,
            status=CompanyStatus.PENDING,
        )
        return new_company, True

    @staticmethod
    async def update_status(
        session: AsyncSession,
        company_id: uuid.UUID,
        status: CompanyStatus,
    ) -> Optional[Company]:
        """Update a company's processing state."""
        company = await CompanyRepository.get_by_id(session, company_id)
        if company:
            company.status = status
            await session.flush()
        return company

    @staticmethod
    async def acquire_lease(
        session: AsyncSession,
        company_id: uuid.UUID,
        lease_duration_minutes: int = 5,
    ) -> bool:
        """
        Atomically acquire a processing lease lock on a company.
        Returns True if acquired, False if already leased by another active worker.
        """
        now = datetime.now(timezone.utc)
        company = await CompanyRepository.get_by_id(session, company_id)
        if not company:
            return False

        # Allow lease if pending or expired
        if company.status == CompanyStatus.PENDING or (
            company.lease_expires_at and company.lease_expires_at < now
        ) or company.status == CompanyStatus.FAILED:
            company.status = CompanyStatus.PROCESSING
            company.lease_expires_at = now + timedelta(minutes=lease_duration_minutes)
            await session.flush()
            return True
        return False

    @staticmethod
    async def get_pending_companies(
        session: AsyncSession,
        limit: int = 20,
    ) -> list[Company]:
        """Retrieve companies in PENDING state awaiting processing."""
        stmt = (
            select(Company)
            .where(Company.status == CompanyStatus.PENDING)
            .order_by(Company.created_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_companies(
        session: AsyncSession,
        status: Optional[CompanyStatus] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Company], int]:
        """Query companies with pagination and optional status/search filters."""
        query = select(Company)
        count_query = select(func.count()).select_from(Company)

        if status:
            query = query.where(Company.status == status)
            count_query = count_query.where(Company.status == status)

        if search:
            search_pattern = f"%{search}%"
            filter_expr = or_(
                Company.name.ilike(search_pattern),
                Company.website_url.ilike(search_pattern),
                Company.domain.ilike(search_pattern),
            )
            query = query.where(filter_expr)
            count_query = count_query.where(filter_expr)

        query = query.order_by(Company.created_at.desc()).limit(limit).offset(offset)

        total_result = await session.execute(count_query)
        total = total_result.scalar_one()

        items_result = await session.execute(
            query.options(selectinload(Company.verdicts))
        )
        items = list(items_result.scalars().all())

        return items, total


class SignalRepository:
    """Repository operations for Signal entities."""

    @staticmethod
    async def create(
        session: AsyncSession,
        company_id: uuid.UUID,
        signal_type: SignalType,
        source_url: str,
        extracted_facts: dict[str, Any],
        raw_data: Optional[dict[str, Any]] = None,
        status: SignalStatus = SignalStatus.SUCCESS,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Signal:
        """Insert a newly extracted evidence signal."""
        signal = Signal(
            company_id=company_id,
            signal_type=signal_type,
            source_url=source_url,
            extracted_facts=extracted_facts,
            raw_data=raw_data,
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
        )
        session.add(signal)
        await session.flush()
        return signal

    @staticmethod
    async def list_by_company(
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[Signal]:
        """Fetch all evidence signals collected for a company."""
        stmt = (
            select(Signal)
            .where(Signal.company_id == company_id)
            .order_by(Signal.collected_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class VerdictRepository:
    """Repository operations for Verdict entities."""

    @staticmethod
    async def create(
        session: AsyncSession,
        company_id: uuid.UUID,
        fit: FitDecision,
        confidence: float,
        reasoning: list[str],
        confidence_rationale: Optional[str] = None,
        follow_up_question: Optional[str] = None,
        key_signals_used: Optional[list[str]] = None,
        rubric_version: Optional[str] = None,
    ) -> Verdict:
        """Persist a structured LLM judgment verdict."""
        verdict = Verdict(
            company_id=company_id,
            fit=fit,
            confidence=confidence,
            reasoning=reasoning,
            confidence_rationale=confidence_rationale,
            follow_up_question=follow_up_question,
            key_signals_used=key_signals_used,
            rubric_version=rubric_version,
        )
        session.add(verdict)
        await session.flush()
        return verdict

    @staticmethod
    async def get_latest_by_company(
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> Optional[Verdict]:
        """Retrieve the most recent evaluation verdict for a company."""
        stmt = (
            select(Verdict)
            .where(Verdict.company_id == company_id)
            .order_by(Verdict.evaluated_at.desc(), Verdict.id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_company(
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[Verdict]:
        """Retrieve all historical evaluation verdicts for a company."""
        stmt = (
            select(Verdict)
            .where(Verdict.company_id == company_id)
            .order_by(Verdict.evaluated_at.desc(), Verdict.id.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class SyncLogRepository:
    """Repository operations for Google Sheets sync audit logs."""

    @staticmethod
    async def create(
        session: AsyncSession,
        company_id: uuid.UUID,
        sync_direction: SyncDirection,
        status: SyncStatus,
        error_details: Optional[str] = None,
    ) -> SyncLog:
        """Record a synchronization attempt."""
        sync_log = SyncLog(
            company_id=company_id,
            sync_direction=sync_direction,
            status=status,
            error_details=error_details,
        )
        session.add(sync_log)
        await session.flush()
        return sync_log

    @staticmethod
    async def list_by_company(
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[SyncLog]:
        """List sync audit logs for a company."""
        stmt = (
            select(SyncLog)
            .where(SyncLog.company_id == company_id)
            .order_by(SyncLog.synced_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class PipelineRunRepository:
    """Repository operations for batch pipeline telemetry records."""

    @staticmethod
    async def create(
        session: AsyncSession,
        trigger_type: TriggerType,
        status: PipelineRunStatus = PipelineRunStatus.RUNNING,
    ) -> PipelineRun:
        """Initialize a new pipeline run execution record."""
        run = PipelineRun(
            trigger_type=trigger_type,
            status=status,
        )
        session.add(run)
        await session.flush()
        return run

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        run_id: uuid.UUID,
    ) -> Optional[PipelineRun]:
        """Find a pipeline run by its unique ID."""
        stmt = select(PipelineRun).where(PipelineRun.id == run_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_counters(
        session: AsyncSession,
        run_id: uuid.UUID,
        total_companies: Optional[int] = None,
        processed_count: Optional[int] = None,
        success_count: Optional[int] = None,
        failed_extraction_count: Optional[int] = None,
        failed_evaluation_count: Optional[int] = None,
        synced_count: Optional[int] = None,
        fit_yes_count: Optional[int] = None,
        fit_no_count: Optional[int] = None,
        fit_uncertain_count: Optional[int] = None,
    ) -> Optional[PipelineRun]:
        """Update telemetry metrics on an active pipeline run."""
        run = await PipelineRunRepository.get_by_id(session, run_id)
        if run:
            if total_companies is not None:
                run.total_companies = total_companies
            if processed_count is not None:
                run.processed_count = processed_count
            if success_count is not None:
                run.success_count = success_count
            if failed_extraction_count is not None:
                run.failed_extraction_count = failed_extraction_count
            if failed_evaluation_count is not None:
                run.failed_evaluation_count = failed_evaluation_count
            if synced_count is not None:
                run.synced_count = synced_count
            if fit_yes_count is not None:
                run.fit_yes_count = fit_yes_count
            if fit_no_count is not None:
                run.fit_no_count = fit_no_count
            if fit_uncertain_count is not None:
                run.fit_uncertain_count = fit_uncertain_count
            await session.flush()
        return run

    @staticmethod
    async def complete_run(
        session: AsyncSession,
        run_id: uuid.UUID,
        status: PipelineRunStatus = PipelineRunStatus.COMPLETED,
        error_summary: Optional[dict[str, Any]] = None,
    ) -> Optional[PipelineRun]:
        """Finalize a pipeline execution with duration and terminal status."""
        run = await PipelineRunRepository.get_by_id(session, run_id)
        if run:
            now = datetime.now(timezone.utc)
            run.status = status
            run.completed_at = now
            if run.started_at:
                started = run.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                run.duration_seconds = (now - started).total_seconds()
            if error_summary:
                run.error_summary = error_summary
            await session.flush()
        return run
