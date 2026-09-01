"""Tests for SQLAlchemy domain models and entity relationships."""

import pytest
from sqlalchemy import select
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


@pytest.mark.asyncio
async def test_company_creation_and_fields(db_session: AsyncSession) -> None:
    """Test creating a company with required and optional fields."""
    company = Company(
        name="Acme Corp",
        website_url="https://acme.com",
        domain="acme.com",
        sheet_row_id="row_10",
        status=CompanyStatus.PENDING,
    )
    db_session.add(company)
    await db_session.commit()

    assert company.id is not None
    assert company.name == "Acme Corp"
    assert company.status == CompanyStatus.PENDING
    assert company.sheet_row_id == "row_10"
    assert company.created_at is not None


@pytest.mark.asyncio
async def test_company_relationships_and_cascade(db_session: AsyncSession) -> None:
    """Test relationships between Company, Signals, Verdicts, and SyncLogs with cascade delete."""
    company = Company(
        name="TechNova Inc",
        website_url="https://technova.io",
        sheet_row_id="row_11",
        status=CompanyStatus.ENRICHED,
    )
    db_session.add(company)
    await db_session.flush()

    # Add multiple signals
    sig1 = Signal(
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        status=SignalStatus.SUCCESS,
        source_url="https://technova.io",
        extracted_facts={"title": "TechNova Cloud"},
    )
    sig2 = Signal(
        company_id=company.id,
        signal_type=SignalType.BROWSER_CAREERS,
        status=SignalStatus.SUCCESS,
        source_url="https://technova.io/careers",
        extracted_facts={"open_jobs": 4, "tech": ["Python", "FastAPI"]},
    )
    # Add verdict
    verdict = Verdict(
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.95,
        reasoning=["Strong B2B enterprise offering", "Hiring Python engineers"],
        follow_up_question="What is their target cloud deployment model?",
    )
    # Add sync log
    sync_log = SyncLog(
        company_id=company.id,
        sync_direction=SyncDirection.DB_TO_SHEET,
        status=SyncStatus.SUCCESS,
    )

    db_session.add_all([sig1, sig2, verdict, sync_log])
    await db_session.commit()

    # Query company with eager-loaded relationships
    stmt = (
        select(Company)
        .where(Company.id == company.id)
        .options(
            selectinload(Company.signals),
            selectinload(Company.verdicts),
            selectinload(Company.sync_logs),
        )
    )
    result = await db_session.execute(stmt)
    fetched_company = result.scalar_one()

    # Verify relationships
    assert len(fetched_company.signals) == 2
    assert len(fetched_company.verdicts) == 1
    assert len(fetched_company.sync_logs) == 1
    assert fetched_company.verdicts[0].fit == FitDecision.YES

    # Test cascade deletion
    await db_session.delete(fetched_company)
    await db_session.commit()

    # Verify children are deleted
    signals_count = await db_session.scalar(select(Signal).where(Signal.company_id == company.id))
    verdicts_count = await db_session.scalar(select(Verdict).where(Verdict.company_id == company.id))
    sync_logs_count = await db_session.scalar(select(SyncLog).where(SyncLog.company_id == company.id))

    assert signals_count is None
    assert verdicts_count is None
    assert sync_logs_count is None


@pytest.mark.asyncio
async def test_pipeline_run_model(db_session: AsyncSession) -> None:
    """Test PipelineRun model creation, counters, and metrics."""
    run = PipelineRun(
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
        total_companies=5,
        processed_count=2,
    )
    db_session.add(run)
    await db_session.commit()

    assert run.id is not None
    assert run.status == PipelineRunStatus.RUNNING
    assert run.total_companies == 5
    assert run.processed_count == 2
    assert run.started_at is not None
