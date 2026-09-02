"""Tests for the database repository data access layer."""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SignalRepository,
    SyncLogRepository,
    VerdictRepository,
)


@pytest.mark.asyncio
async def test_company_repository_crud(db_session: AsyncSession) -> None:
    """Test CompanyRepository create, get_by_id, and update_status operations."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Apex Systems",
        website_url="https://apex.io",
        sheet_row_id="row_101",
        domain="apex.io",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    fetched = await CompanyRepository.get_by_id(db_session, company.id)
    assert fetched is not None
    assert fetched.name == "Apex Systems"
    assert fetched.sheet_row_id == "row_101"

    updated = await CompanyRepository.update_status(db_session, company.id, CompanyStatus.PROCESSING)
    await db_session.commit()
    assert updated is not None
    assert updated.status == CompanyStatus.PROCESSING


@pytest.mark.asyncio
async def test_company_repository_idempotent_upsert(db_session: AsyncSession) -> None:
    """Test that upsert_by_sheet_row_id creates new companies and updates existing ones idempotently."""
    company1, created1 = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="Beta Labs",
        website_url="https://betalabs.com",
        sheet_row_id="row_202",
        domain="betalabs.com",
    )
    await db_session.commit()
    assert created1 is True
    assert company1.sheet_row_id == "row_202"

    # Second upsert with same sheet_row_id should update, not create duplicate
    company2, created2 = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="Beta Labs Updated",
        website_url="https://betalabs.com/new",
        sheet_row_id="row_202",
        domain="betalabs.com",
    )
    await db_session.commit()
    assert created2 is False
    assert company2.id == company1.id
    assert company2.name == "Beta Labs Updated"
    assert company2.website_url == "https://betalabs.com/new"


@pytest.mark.asyncio
async def test_company_sheet_row_id_unique_constraint(db_session: AsyncSession) -> None:
    """Test that direct duplicate sheet_row_id insertion raises IntegrityError."""
    await CompanyRepository.create(
        session=db_session,
        name="First Company",
        website_url="https://first.com",
        sheet_row_id="row_dup_test",
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await CompanyRepository.create(
            session=db_session,
            name="Duplicate Row Company",
            website_url="https://duplicate.com",
            sheet_row_id="row_dup_test",
        )
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_company_repository_lease_locking(db_session: AsyncSession) -> None:
    """Test atomic lease locking for concurrency protection."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Gamma Cloud",
        website_url="https://gamma.io",
        sheet_row_id="row_303",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    # First lease acquisition should succeed
    leased = await CompanyRepository.acquire_lease(db_session, company.id, lease_duration_minutes=5)
    await db_session.commit()
    assert leased is True

    # Immediate second acquisition should be blocked
    second_lease = await CompanyRepository.acquire_lease(db_session, company.id, lease_duration_minutes=5)
    assert second_lease is False


@pytest.mark.asyncio
async def test_company_repository_query_filtering_and_pagination(db_session: AsyncSession) -> None:
    """Test querying companies with status filters, search, and pagination."""
    await CompanyRepository.create(
        session=db_session,
        name="Alpha Searchable",
        website_url="https://alpha.com",
        sheet_row_id="row_p1",
        status=CompanyStatus.PENDING,
    )
    await CompanyRepository.create(
        session=db_session,
        name="Bravo Other",
        website_url="https://bravo.com",
        sheet_row_id="row_p2",
        status=CompanyStatus.SYNCED,
    )
    await CompanyRepository.create(
        session=db_session,
        name="Alpha Secondary",
        website_url="https://alphasecondary.com",
        sheet_row_id="row_p3",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    # Test pending filter
    pending = await CompanyRepository.get_pending_companies(db_session, limit=10)
    assert len(pending) == 2

    # Test search filter
    items, total = await CompanyRepository.list_companies(db_session, search="Alpha")
    assert total == 2
    assert len(items) == 2

    # Test status filter
    synced_items, synced_total = await CompanyRepository.list_companies(
        db_session, status=CompanyStatus.SYNCED
    )
    assert synced_total == 1
    assert synced_items[0].name == "Bravo Other"


@pytest.mark.asyncio
async def test_signal_repository_operations(db_session: AsyncSession) -> None:
    """Test inserting and querying multiple independent evidence signals."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Signal Test Co",
        website_url="https://signals.io",
        sheet_row_id="row_sig_1",
    )
    await db_session.commit()

    # Add HTTP signal
    sig1 = await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        source_url="https://signals.io",
        extracted_facts={"title": "Signals IO", "h1": "Next-Gen Data"},
        duration_ms=250,
    )

    # Add Playwright browser signal
    sig2 = await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.BROWSER_CAREERS,
        source_url="https://signals.io/careers",
        extracted_facts={"active_jobs": 8, "departments": ["Engineering"]},
        duration_ms=2100,
    )
    await db_session.commit()

    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 2
    assert signals[0].signal_type == SignalType.HTTP_WEBSITE
    assert signals[1].signal_type == SignalType.BROWSER_CAREERS


@pytest.mark.asyncio
async def test_verdict_repository_operations(db_session: AsyncSession) -> None:
    """Test persisting and retrieving latest LLM evaluation verdicts."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Verdict Test Co",
        website_url="https://verdict.io",
        sheet_row_id="row_verd_1",
    )
    await db_session.commit()

    verdict1 = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.UNCERTAIN,
        confidence=0.35,
        reasoning=["Initial partial evidence"],
        rubric_version="1.0.0",
    )
    await db_session.commit()

    # Add a newer verdict
    verdict2 = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.92,
        reasoning=["Confirmed enterprise B2B offering", "Active hiring"],
        follow_up_question="Do they support SSO/SAML?",
        rubric_version="1.1.0",
    )
    await db_session.commit()

    latest = await VerdictRepository.get_latest_by_company(db_session, company.id)
    assert latest is not None
    assert latest.fit == FitDecision.YES
    assert latest.confidence == 0.92
    assert latest.rubric_version == "1.1.0"

    history = await VerdictRepository.list_by_company(db_session, company.id)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_sync_log_repository_operations(db_session: AsyncSession) -> None:
    """Test recording and querying synchronization audit logs."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Sync Test Co",
        website_url="https://synctest.io",
        sheet_row_id="row_sync_1",
    )
    await db_session.commit()

    log = await SyncLogRepository.create(
        session=db_session,
        company_id=company.id,
        sync_direction=SyncDirection.DB_TO_SHEET,
        status=SyncStatus.SUCCESS,
    )
    await db_session.commit()

    logs = await SyncLogRepository.list_by_company(db_session, company.id)
    assert len(logs) == 1
    assert logs[0].status == SyncStatus.SUCCESS
    assert logs[0].sync_direction == SyncDirection.DB_TO_SHEET


@pytest.mark.asyncio
async def test_pipeline_run_repository_lifecycle(db_session: AsyncSession) -> None:
    """Test creating, updating telemetry counters, and completing a pipeline run."""
    run = await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.SCHEDULED,
    )
    await db_session.commit()
    assert run.status == PipelineRunStatus.RUNNING

    # Update counters
    updated = await PipelineRunRepository.update_counters(
        session=db_session,
        run_id=run.id,
        total_companies=10,
        processed_count=10,
        success_count=9,
        failed_extraction_count=1,
        fit_yes_count=5,
        fit_no_count=4,
    )
    await db_session.commit()
    assert updated.processed_count == 10
    assert updated.success_count == 9

    # Complete run
    completed = await PipelineRunRepository.complete_run(
        session=db_session,
        run_id=run.id,
        status=PipelineRunStatus.COMPLETED,
    )
    await db_session.commit()
    assert completed.status == PipelineRunStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.duration_seconds is not None
