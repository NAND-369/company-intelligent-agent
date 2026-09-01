"""Comprehensive tests for the Phase 8 Google Sheets Synchronization subsystem."""

from datetime import datetime, timezone
import json
from typing import Any, Optional
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SyncDirection,
    SyncStatus,
    TriggerType,
)
from app.database.models import Company, SyncLog, Verdict
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SyncLogRepository,
    VerdictRepository,
)
from app.integrations.google_sheets.client import (
    GoogleSheetsAPIError,
    GoogleSheetsClientProtocol,
    SpreadsheetNotFoundError,
)
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest
from app.sync.column_mapper import SheetColumnMapper
from app.sync.schemas import SyncOutcome
from app.sync.sheets_sync_service import SheetsSyncService


class MockGoogleSheetsSyncClient:
    """Mock Sheets client tracking cell updates and supporting transient error injection."""

    def __init__(
        self,
        headers: Optional[list[str]] = None,
        transient_failures_remaining: int = 0,
        permanent_error: Optional[Exception] = None,
    ) -> None:
        self.headers = headers or [
            "Company Name",
            "Website",
            "Status",
            "Fit",
            "Confidence",
            "Reasoning",
            "Follow-up Question",
            "Last Synced",
        ]
        self.row_updates: dict[int, dict[int, Any]] = {}
        self.transient_failures_remaining = transient_failures_remaining
        self.permanent_error = permanent_error
        self.call_count = 0

    def get_header_row(self, spreadsheet_id: str, worksheet_name: str) -> list[str]:
        return self.headers

    def get_rows_with_indices(self, spreadsheet_id: str, worksheet_name: str) -> list[tuple[int, dict[str, Any]]]:
        return []

    def update_row_cells(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        row_index: int,
        updates_by_col_index: dict[int, Any],
    ) -> bool:
        self.call_count += 1

        if self.permanent_error:
            raise self.permanent_error

        if self.transient_failures_remaining > 0:
            self.transient_failures_remaining -= 1
            raise GoogleSheetsAPIError("429 Resource exhausted: Quota exceeded")

        self.row_updates[row_index] = updates_by_col_index
        return True


# ==============================================================================
# 1. Column Mapper & Formatting Tests
# ==============================================================================

def test_column_mapper_resolves_standard_and_alias_headers() -> None:
    """Verify that SheetColumnMapper identifies standard columns and aliases."""
    headers = [
        "Company Name",
        "Website",
        "Status",
        "Recommendation",
        "Confidence Score",
        "Evidence Reasoning",
        "Discovery Question",
        "Timestamp",
    ]
    mapper = SheetColumnMapper(headers=headers)
    mapping = mapper.mapped_fields

    assert mapping["status"] == 3
    assert mapping["fit"] == 4
    assert mapping["confidence"] == 5
    assert mapping["reasoning"] == 6
    assert mapping["follow_up_question"] == 7
    assert mapping["last_synced"] == 8


def test_column_mapper_formats_verdict_cells() -> None:
    """Test formatting of Verdict model into cell updates."""
    headers = ["Company Name", "Website", "Status", "Fit", "Confidence", "Reasoning", "Follow-up Question", "Last Synced"]
    mapper = SheetColumnMapper(headers=headers)

    verdict = Verdict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        fit=FitDecision.YES,
        confidence=0.88,
        reasoning=["B2B SaaS product.", "Active engineering hiring."],
        follow_up_question="What is the current tech stack?",
        rubric_version="v1.0",
    )
    company = Company(id=verdict.company_id, name="Test Co", website_url="https://test.com", sheet_row_id="row_3")

    col_updates, readable = mapper.format_updates(verdict, company)

    assert col_updates[3] == "SYNCED"  # Status
    assert col_updates[4] == "YES"     # Fit
    assert col_updates[5] == "0.88"    # Confidence
    assert "1. B2B SaaS product." in col_updates[6]  # Reasoning
    assert col_updates[7] == "What is the current tech stack?"  # Follow-up
    assert readable["fit"] == "YES"


# ==============================================================================
# 2. Single & Multi-Company Synchronization Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_sync_single_company_success(db_session: AsyncSession) -> None:
    """Test successful synchronization of one evaluated company to Google Sheets."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Alpha Robotics",
        website_url="https://alpha-robotics.com",
        sheet_row_id="row_4",
        status=CompanyStatus.JUDGED,
    )
    verdict = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.95,
        reasoning=["Robotics hardware and autonomous software."],
        follow_up_question="Do you support ROS2?",
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    result = await service.sync_company(company_id=company.id)

    assert result.status == SyncOutcome.SUCCESS
    assert result.row_index == 4
    assert 4 in mock_client.row_updates
    assert mock_client.row_updates[4][4] == "YES"  # Fit column

    # Verify PostgreSQL state updated to SYNCED
    updated_co = await CompanyRepository.get_by_id(db_session, company.id)
    assert updated_co.status == CompanyStatus.SYNCED

    # Verify SyncLog created
    logs = await SyncLogRepository.list_by_company(db_session, company.id)
    assert len(logs) == 1
    assert logs[0].sync_direction == SyncDirection.DB_TO_SHEET
    assert logs[0].status == SyncStatus.SUCCESS


@pytest.mark.asyncio
async def test_sync_batch_multiple_companies(db_session: AsyncSession) -> None:
    """Test batch synchronization of multiple evaluated companies."""
    co1 = await CompanyRepository.create(session=db_session, name="Co 1", website_url="https://co1.com", sheet_row_id="row_2", status=CompanyStatus.JUDGED)
    co2 = await CompanyRepository.create(session=db_session, name="Co 2", website_url="https://co2.com", sheet_row_id="row_3", status=CompanyStatus.JUDGED)
    await VerdictRepository.create(session=db_session, company_id=co1.id, fit=FitDecision.YES, confidence=0.85, reasoning=["Fits ICP"])
    await VerdictRepository.create(session=db_session, company_id=co2.id, fit=FitDecision.NO, confidence=0.90, reasoning=["B2C focus"])
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    batch_res = await service.sync_evaluated_companies(spreadsheet_id="test_sheet_id")

    assert batch_res.total_candidates == 2
    assert batch_res.synced_count == 2
    assert batch_res.failed_count == 0
    assert 2 in mock_client.row_updates
    assert 3 in mock_client.row_updates


# ==============================================================================
# 3. Idempotency & Resumability Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_sync_idempotency_skips_unchanged_verdict(db_session: AsyncSession) -> None:
    """Verify that repeated sync for an already synced company with unchanged verdict is skipped."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Idempotent Sync Co",
        website_url="https://idem-sync.com",
        sheet_row_id="row_5",
        status=CompanyStatus.JUDGED,
    )
    await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.80,
        reasoning=["Target fit."],
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    # First Sync -> SUCCESS
    res1 = await service.sync_company(company_id=company.id)
    assert res1.status == SyncOutcome.SUCCESS
    assert mock_client.call_count == 1

    # Second Sync -> SKIPPED (Idempotent)
    res2 = await service.sync_company(company_id=company.id)
    assert res2.status == SyncOutcome.SKIPPED
    assert mock_client.call_count == 1  # No additional Sheets API write call


@pytest.mark.asyncio
async def test_sync_changed_verdict_re_synchronizes(db_session: AsyncSession) -> None:
    """Verify that if a verdict changes, sync proceeds even if previously synced."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Dynamic Verdict Co",
        website_url="https://dyn-verdict.com",
        sheet_row_id="row_6",
        status=CompanyStatus.SYNCED,
    )
    # Simulate existing sync log
    await SyncLogRepository.create(session=db_session, company_id=company.id, sync_direction=SyncDirection.DB_TO_SHEET, status=SyncStatus.SUCCESS)
    # Add new revised verdict
    await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.NO,
        confidence=0.92,
        reasoning=["Disqualified on manual review."],
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    # Force sync on new verdict
    res = await service.sync_company(company_id=company.id, force=True)
    assert res.status == SyncOutcome.SUCCESS
    assert 6 in mock_client.row_updates


# ==============================================================================
# 4. Failure Isolation & Transient Error Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_sync_failure_isolation_one_bad_company(db_session: AsyncSession) -> None:
    """Verify that failure on one company (missing row ID) does not block others."""
    co_good = await CompanyRepository.create(session=db_session, name="Good Co", website_url="https://good.com", sheet_row_id="row_7", status=CompanyStatus.JUDGED)
    co_bad = await CompanyRepository.create(session=db_session, name="Bad Co", website_url="https://bad.com", sheet_row_id="", status=CompanyStatus.JUDGED)
    await VerdictRepository.create(session=db_session, company_id=co_good.id, fit=FitDecision.YES, confidence=0.9, reasoning=["Fits"])
    await VerdictRepository.create(session=db_session, company_id=co_bad.id, fit=FitDecision.YES, confidence=0.9, reasoning=["Fits"])
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    batch_res = await service.sync_evaluated_companies(spreadsheet_id="test_sheet_id")

    assert batch_res.total_candidates == 2
    assert batch_res.synced_count == 1
    assert batch_res.failed_count == 1
    assert 7 in mock_client.row_updates


@pytest.mark.asyncio
async def test_sync_dry_run_makes_no_api_calls(db_session: AsyncSession) -> None:
    """Verify that dry-run mode previews updates without calling Google Sheets API."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Dry Run Sync Co",
        website_url="https://dry-sync.com",
        sheet_row_id="row_8",
        status=CompanyStatus.JUDGED,
    )
    await VerdictRepository.create(session=db_session, company_id=company.id, fit=FitDecision.YES, confidence=0.85, reasoning=["Good fit"])
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    result = await service.sync_company(company_id=company.id, dry_run=True)

    assert result.status == SyncOutcome.SUCCESS
    assert mock_client.call_count == 0  # Zero API write calls
    assert len(mock_client.row_updates) == 0

    # Company status remains JUDGED (not mutated)
    co = await CompanyRepository.get_by_id(db_session, company.id)
    assert co.status == CompanyStatus.JUDGED


# ==============================================================================
# 5. Pipeline Orchestrator Integration with Sheets Sync
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_orchestration_with_sync_stage(db_session: AsyncSession) -> None:
    """Test full pipeline run with sync_to_sheets=True."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Pipeline Sync Co",
        website_url="https://pipe-sync.com",
        sheet_row_id="row_9",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    sync_service = SheetsSyncService(session=db_session, client=mock_client)

    orchestrator = PipelineOrchestrator(
        session=db_session,
        sync_service=sync_service,
    )

    result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            skip_ingestion=True,
            sync_to_sheets=True,
        )
    )

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_processed == 1
    assert result.synced_count == 1
    assert 9 in mock_client.row_updates

    # Verify company final status in PostgreSQL is SYNCED
    co = await CompanyRepository.get_by_id(db_session, company.id)
    assert co.status == CompanyStatus.SYNCED


# ==============================================================================
# 6. FastAPI API Endpoint Sync Flag Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_api_trigger_pipeline_with_sync_flag(async_client: AsyncClient) -> None:
    """Test triggering pipeline with sync_to_sheets=True via REST API."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    response = await async_client.post(
        "/pipeline/run",
        json={"dry_run": True, "skip_ingestion": True, "sync_to_sheets": True},
        headers=headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"
