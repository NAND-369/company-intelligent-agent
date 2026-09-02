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
from app.integrations.google_sheets.service import CompanyIngestionService
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

    def find_company_row(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        company_name: str,
        website_url: Optional[str] = None,
    ) -> Optional[int]:
        return None

    def append_row_values(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        updates_by_col_index: dict[int, Any],
    ) -> int:
        self.call_count += 1
        if self.permanent_error:
            raise self.permanent_error
        new_row_idx = max(len(self.row_updates) + 2, 2)
        self.row_updates[new_row_idx] = updates_by_col_index
        return new_row_idx

    def ensure_header_columns(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        required_headers: list[str],
    ) -> list[str]:
        return self.headers


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
    """Verify that failure on one company (missing verdict) does not block others."""
    co_good = await CompanyRepository.create(session=db_session, name="Good Co", website_url="https://good.com", sheet_row_id="row_7", status=CompanyStatus.JUDGED)
    co_bad = await CompanyRepository.create(session=db_session, name="Bad Co", website_url="https://bad.com", sheet_row_id="row_8", status=CompanyStatus.JUDGED)
    await VerdictRepository.create(session=db_session, company_id=co_good.id, fit=FitDecision.YES, confidence=0.9, reasoning=["Fits"])
    # co_bad has no verdict created -> sync will fail for co_bad while co_good succeeds
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


@pytest.mark.asyncio
async def test_pipeline_force_reprocess_overwrites_sheets_sync(db_session: AsyncSession) -> None:
    """
    Test that when a company is already SYNCED, running with force_reprocess=True and sync_to_sheets=True:
    1. Discovers the SYNCED company.
    2. Re-evaluates company with LLM judge.
    3. Forces Google Sheets row overwrite.
    4. Records sync audit log and leaves company in SYNCED status.
    """
    company = await CompanyRepository.create(
        session=db_session,
        name="Forced Sync Co",
        website_url="https://forced-sync.com",
        sheet_row_id="row_10",
        status=CompanyStatus.SYNCED,
    )
    # Simulate initial verdict and sync log
    await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.UNCERTAIN,
        confidence=0.35,
        reasoning=["Initial low confidence"],
    )
    await SyncLogRepository.create(
        session=db_session,
        company_id=company.id,
        sync_direction=SyncDirection.DB_TO_SHEET,
        status=SyncStatus.SUCCESS,
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    sync_service = SheetsSyncService(session=db_session, client=mock_client)
    orchestrator = PipelineOrchestrator(session=db_session, sync_service=sync_service)

    # 1. Normal run skips the SYNCED company
    res_normal = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=True, force_reprocess=False)
    )
    assert res_normal.companies_discovered == 0
    assert mock_client.call_count == 0

    # 2. Forced run discovers and re-syncs to row 10
    res_forced = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=True, force_reprocess=True)
    )
    assert res_forced.companies_discovered == 1
    assert res_forced.companies_processed == 1
    assert res_forced.synced_count == 1
    assert 10 in mock_client.row_updates
    assert mock_client.call_count == 1


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


@pytest.mark.asyncio
async def test_api_sheets_sync_endpoint(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test on-demand sheets ingestion endpoint POST /sheets/sync."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    from app.integrations.google_sheets.schemas import IngestionResult
    from app.integrations.google_sheets.service import CompanyIngestionService

    async def mock_ingest(self):
        return IngestionResult(
            spreadsheet_id="test-sheet",
            worksheet_name="Companies",
            rows_read=2,
            companies_created=1,
            companies_updated=1,
            rows_skipped=0,
        )

    monkeypatch.setattr(CompanyIngestionService, "ingest_companies", mock_ingest)

    response = await async_client.post("/sheets/sync", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["rows_read"] == 2
    assert data["companies_created"] == 1
    assert data["companies_updated"] == 1


@pytest.mark.asyncio
async def test_sync_missing_sheet_row_id_auto_appends_row(db_session: AsyncSession) -> None:
    """Verify that a company added without sheet_row_id is automatically appended to Google Sheets."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Auto Append Corp",
        website_url="https://autoappend.io",
        sheet_row_id=None,
        status=CompanyStatus.JUDGED,
    )
    await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.98,
        reasoning=["Enterprise B2B platform."],
    )
    await db_session.commit()

    mock_client = MockGoogleSheetsSyncClient()
    service = SheetsSyncService(session=db_session, client=mock_client)

    result = await service.sync_company(company_id=company.id, spreadsheet_id="test_sheet_id")

    assert result.status == SyncOutcome.SUCCESS
    assert result.row_index >= 2
    assert result.sheet_row_id == f"row_{result.row_index}"

    # Verify company updated in database
    updated = await CompanyRepository.get_by_id(db_session, company.id)
    assert updated.sheet_row_id == f"row_{result.row_index}"
    assert updated.status == CompanyStatus.SYNCED


@pytest.mark.asyncio
async def test_sync_failure_does_not_corrupt_or_lose_verdict(db_session: AsyncSession) -> None:
    """Verify that a Google Sheets API failure logs the error without corrupting or deleting the persisted DB verdict."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Fail Sync Corp",
        website_url="https://failsync.io",
        sheet_row_id="row_5",
        status=CompanyStatus.JUDGED,
    )
    verdict = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.98,
        reasoning=["Solid B2B enterprise software."],
    )
    await db_session.commit()

    failing_client = MockGoogleSheetsSyncClient(permanent_error=GoogleSheetsAPIError("Permission denied: 403"))
    service = SheetsSyncService(session=db_session, client=failing_client)

    result = await service.sync_company(company_id=company.id, spreadsheet_id="test_sheet_id")

    assert result.status == SyncOutcome.FAILED
    assert "Permission denied" in result.error_details

    # Verify verdict in database is completely intact
    latest_verdict = await VerdictRepository.get_latest_by_company(db_session, company.id)
    assert latest_verdict is not None
    assert latest_verdict.id == verdict.id
    assert latest_verdict.fit == FitDecision.YES
    assert latest_verdict.confidence == 0.98


@pytest.mark.asyncio
async def test_sheet_sync_and_manual_input_converge_no_duplicates(db_session: AsyncSession) -> None:
    """Verify that manual entry and sheet ingestion for the same domain converge to a single DB entity."""
    # 1. Manual addition
    manual_co = await CompanyRepository.create(
        session=db_session,
        name="Anthropic",
        website_url="https://www.anthropic.com",
        domain="anthropic.com",
        sheet_row_id=None,
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    # 2. Ingest from Sheet (row 2)
    mock_client = MockGoogleSheetsSyncClient()
    mock_client.get_rows_with_indices = lambda spreadsheet_id, worksheet_name: [(2, {"Company Name": "Anthropic PBC", "Website": "http://anthropic.com/"})]

    ingestion_service = CompanyIngestionService(session=db_session, client=mock_client)
    res = await ingestion_service.ingest_companies(spreadsheet_id="test_sheet")

    assert res.companies_created == 0
    assert res.companies_updated == 1
    assert len(res.imported_companies) == 1
    assert res.imported_companies[0]["id"] == str(manual_co.id)
    assert res.imported_companies[0]["sheet_row_id"] == "row_2"

    # Verify single entity in database
    company = await CompanyRepository.get_by_id(db_session, manual_co.id)
    assert company.sheet_row_id == "row_2"
    assert company.domain == "anthropic.com"


@pytest.mark.asyncio
async def test_domain_normalization_and_upsert_identity(db_session: AsyncSession) -> None:
    """Verify that varied URL formats match the same canonical company entity."""
    co1, created1 = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="Datadog",
        website_url="https://www.datadoghq.com/",
        sheet_row_id="row_4",
        domain="datadoghq.com",
    )
    await db_session.commit()
    assert created1 is True

    # Upsert with different URL variation and name case
    co2, created2 = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="Datadog HQ",
        website_url="http://datadoghq.com",
        sheet_row_id="row_4",
        domain="datadoghq.com",
    )
    await db_session.commit()
    assert created2 is False
    assert co1.id == co2.id
    assert co2.name == "Datadog HQ"


@pytest.mark.asyncio
async def test_changed_sheet_row_domain_resets_status_to_pending(db_session: AsyncSession) -> None:
    """Verify that changing a sheet row's domain marks it as PENDING for re-evaluation."""
    company, _ = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="Old Tech",
        website_url="https://oldtech.io",
        sheet_row_id="row_6",
        domain="oldtech.io",
    )
    company.status = CompanyStatus.SYNCED
    await db_session.commit()

    # Now Sheet row 6 changes to a completely new domain
    updated_company, created = await CompanyRepository.upsert_by_sheet_row_id(
        session=db_session,
        name="New Tech Inc",
        website_url="https://newtech.ai",
        sheet_row_id="row_6",
        domain="newtech.ai",
    )
    await db_session.commit()

    assert created is False
    assert updated_company.id == company.id
    assert updated_company.domain == "newtech.ai"
    assert updated_company.status == CompanyStatus.PENDING
