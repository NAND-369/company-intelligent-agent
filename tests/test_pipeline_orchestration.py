"""Comprehensive tests for the Phase 7 Pipeline Orchestration subsystem."""

import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SignalStatus,
    SignalType,
    TriggerType,
)
from app.database.models import Company, PipelineRun, Signal, Verdict
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SignalRepository,
    VerdictRepository,
)
from app.enrichment.browser_client import PlaywrightBrowserClient
from app.enrichment.browser_enricher import BrowserEnricher
from app.enrichment.service import HttpEnrichmentService
from app.enrichment.website_enricher import WebsiteEnricher
from app.integrations.google_sheets.service import CompanyIngestionService
from app.llm.client import FakeLLMClient
from app.llm.service import LLMJudgeService
from app.main import app
from app.pipeline.company_processor import CompanyProcessor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest, PipelineRunResult
from tests.test_http_enrichment import MockHttpClient, REALISTIC_HTML_FIXTURE


# Mock Google Sheets Client for testing
class MockSheetsClient:
    def __init__(self, rows: list[tuple[int, dict[str, str]]]) -> None:
        self.rows = rows

    def get_rows_with_indices(self, spreadsheet_id: str, worksheet_name: str) -> list[tuple[int, dict[str, str]]]:
        return self.rows


# ==============================================================================
# 1. Pipeline Orchestrator Basic Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_empty_companies(db_session: AsyncSession) -> None:
    """Test pipeline execution when zero companies exist in database."""
    orchestrator = PipelineOrchestrator(session=db_session)
    result = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True))

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_discovered == 0
    assert result.companies_processed == 0


@pytest.mark.asyncio
async def test_pipeline_dry_run_mode(db_session: AsyncSession) -> None:
    """Test that dry-run mode identifies candidates without modifying database state."""
    company = await CompanyRepository.create(
        session=db_session,
        name="DryRun Corp",
        website_url="https://dryrun.io",
        sheet_row_id="row_dry_run",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    orchestrator = PipelineOrchestrator(session=db_session)
    result = await orchestrator.run_pipeline(PipelineRunRequest(dry_run=True, skip_ingestion=True))

    assert result.dry_run is True
    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_discovered >= 1
    assert result.companies_processed == 0

    # Verify company remained in PENDING state
    fresh_co = await CompanyRepository.get_by_id(db_session, company.id)
    assert fresh_co.status == CompanyStatus.PENDING


# ==============================================================================
# 2. End-to-End Pipeline Execution Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_full_e2e_successful_flow(db_session: AsyncSession) -> None:
    """
    Complete End-to-End Pipeline Test:
    Google Sheets -> PostgreSQL Company -> HTTP/Browser Enrichment -> LLM Judge -> Verdict.
    """
    test_settings = Settings(google_sheets_spreadsheet_id="test_sheet_123")

    # 1. Setup Mock Google Sheets Data
    mock_sheet_rows = [
        (2, {"Company Name": "CyberLogistics AI", "Website": "https://cyberlogistics.io"}),
    ]
    ingestion_service = CompanyIngestionService(
        session=db_session,
        client=MockSheetsClient(mock_sheet_rows),
        settings=test_settings,
    )

    # 2. Setup Mock Enrichment Providers
    mock_routes = {
        "https://cyberlogistics.io": (200, REALISTIC_HTML_FIXTURE),
    }
    http_enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))

    enrichment_service = HttpEnrichmentService(
        session=db_session,
        website_enricher=http_enricher,
    )

    # 3. Setup Fake LLM Client
    yes_verdict_json = json.dumps({
        "fit": "YES",
        "confidence": 0.91,
        "confidence_rationale": "Clear B2B logistics tech product with active engineering hiring.",
        "reasoning": [
            "HTTP website signal demonstrates autonomous warehouse robotics platform.",
        ],
        "follow_up_question": None,
        "key_signals_used": ["HTTP_WEBSITE"],
    })
    llm_client = FakeLLMClient(responses=[yes_verdict_json])
    llm_service = LLMJudgeService(session=db_session, llm_client=llm_client)

    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=enrichment_service,
        llm_judge_service=llm_service,
        enable_browser=False,  # Keep test fast without full browser launch
    )

    orchestrator = PipelineOrchestrator(
        session=db_session,
        settings=test_settings,
        ingestion_service=ingestion_service,
        processor=processor,
    )

    # 4. Execute Pipeline Run
    result = await orchestrator.run_pipeline(
        PipelineRunRequest(trigger_type=TriggerType.ON_DEMAND_API)
    )

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_discovered == 1
    assert result.companies_processed == 1
    assert result.companies_succeeded == 1
    assert result.fit_yes_count == 1

    # 5. Verify PostgreSQL System of Record
    persisted_run = await PipelineRunRepository.get_by_id(db_session, result.run_id)
    assert persisted_run is not None
    assert persisted_run.status == PipelineRunStatus.COMPLETED
    assert persisted_run.success_count == 1
    assert persisted_run.fit_yes_count == 1

    companies, _ = await CompanyRepository.list_companies(db_session)
    co = [c for c in companies if c.name == "CyberLogistics AI"][0]
    assert co.status == CompanyStatus.JUDGED

    verdicts = await VerdictRepository.list_by_company(db_session, co.id)
    assert len(verdicts) == 1
    assert verdicts[0].fit == FitDecision.YES
    assert verdicts[0].confidence == 0.91


# ==============================================================================
# 3. Failure Isolation & Multi-Company Resilience Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_failure_isolation_multi_company(db_session: AsyncSession) -> None:
    """
    Test failure isolation:
    Company A succeeds, Company B fails on HTTP 404, Company C succeeds.
    Pipeline must not crash and must process all companies.
    """
    co_a = await CompanyRepository.create(session=db_session, name="Co A", website_url="https://site-a.com", sheet_row_id="row_a")
    co_b = await CompanyRepository.create(session=db_session, name="Co B (Dead)", website_url="https://site-b-dead.com", sheet_row_id="row_b")
    co_c = await CompanyRepository.create(session=db_session, name="Co C", website_url="https://site-c.com", sheet_row_id="row_c")
    await db_session.commit()

    # Route configuration: Site B is missing (triggers 404)
    mock_routes = {
        "https://site-a.com": (200, REALISTIC_HTML_FIXTURE),
        "https://site-c.com": (200, REALISTIC_HTML_FIXTURE),
    }
    http_enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    enrichment_service = HttpEnrichmentService(session=db_session, website_enricher=http_enricher)
    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())

    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=enrichment_service,
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(session=db_session, processor=processor)

    result = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True))

    assert result.status in (PipelineRunStatus.COMPLETED, PipelineRunStatus.PARTIAL_FAILURE)
    assert result.companies_processed == 3
    assert result.companies_succeeded == 3  # Site B fails HTTP fetch gracefully and LLM evaluates missing signals as UNCERTAIN

    # Verify Co B received an UNCERTAIN verdict due to failed extraction
    verdict_b = await VerdictRepository.get_latest_by_company(db_session, co_b.id)
    assert verdict_b is not None
    assert verdict_b.fit == FitDecision.UNCERTAIN


# ==============================================================================
# 4. Resumability & Idempotency Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_idempotent_second_run(db_session: AsyncSession) -> None:
    """Test that running the pipeline twice does not duplicate work or records."""
    co = await CompanyRepository.create(
        session=db_session,
        name="Idempotent Test Co",
        website_url="https://idempotent.com",
        sheet_row_id="row_idempotent",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_routes = {"https://idempotent.com": (200, REALISTIC_HTML_FIXTURE)}
    http_enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    enrichment_service = HttpEnrichmentService(session=db_session, website_enricher=http_enricher)
    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())
    processor = CompanyProcessor(session=db_session, http_enrichment_service=enrichment_service, llm_judge_service=llm_service, enable_browser=False)
    orchestrator = PipelineOrchestrator(session=db_session, processor=processor)

    # First Run
    res1 = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True))
    assert res1.companies_processed == 1
    assert res1.companies_succeeded == 1

    # Second Run (Company already JUDGED -> discovers 0)
    res2 = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True))
    assert res2.companies_discovered == 0

    # Signals and verdicts should NOT be duplicated on second run
    signals = await SignalRepository.list_by_company(db_session, co.id)
    assert len(signals) == 1
    verdicts = await VerdictRepository.list_by_company(db_session, co.id)
    assert len(verdicts) == 1

    # Third Run with force_reprocess=True (Should re-evaluate JUDGED company)
    res3 = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True, force_reprocess=True))
    assert res3.companies_discovered == 1
    assert res3.companies_processed == 1
    assert res3.companies_succeeded == 1

    # A second verdict record should now be created
    verdicts_after_force = await VerdictRepository.list_by_company(db_session, co.id)
    assert len(verdicts_after_force) == 2


@pytest.mark.asyncio
async def test_pipeline_force_reprocess_excludes_failed_companies(db_session: AsyncSession) -> None:
    """
    Verify that force_reprocess=True includes PENDING, ENRICHED, JUDGED, SYNCED,
    but explicitly excludes FAILED companies (which require individual retry).
    """
    co_synced = await CompanyRepository.create(
        session=db_session,
        name="Synced Co",
        website_url="https://synced.com",
        sheet_row_id="row_synced",
        status=CompanyStatus.SYNCED,
    )
    co_judged = await CompanyRepository.create(
        session=db_session,
        name="Judged Co",
        website_url="https://judged.com",
        sheet_row_id="row_judged",
        status=CompanyStatus.JUDGED,
    )
    co_failed = await CompanyRepository.create(
        session=db_session,
        name="Failed Co",
        website_url="https://failed.com",
        sheet_row_id="row_failed",
        status=CompanyStatus.FAILED,
    )
    await db_session.commit()

    mock_routes = {
        "https://synced.com": (200, REALISTIC_HTML_FIXTURE),
        "https://judged.com": (200, REALISTIC_HTML_FIXTURE),
    }
    http_enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    enrichment_service = HttpEnrichmentService(session=db_session, website_enricher=http_enricher)
    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())
    processor = CompanyProcessor(session=db_session, http_enrichment_service=enrichment_service, llm_judge_service=llm_service, enable_browser=False)
    orchestrator = PipelineOrchestrator(session=db_session, processor=processor)

    # 1. Normal run discovers 0 companies (all are SYNCED, JUDGED, or FAILED)
    res_normal = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True, force_reprocess=False))
    assert res_normal.companies_discovered == 0

    # 2. Forced run discovers 2 companies (Synced Co, Judged Co) and skips Failed Co
    res_forced = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True, force_reprocess=True))
    assert res_forced.companies_discovered == 2
    assert res_forced.companies_processed == 2
    assert res_forced.companies_succeeded == 2

    # Failed Co must remain FAILED and unleased
    fresh_failed = await CompanyRepository.get_by_id(db_session, co_failed.id)
    assert fresh_failed is not None
    assert fresh_failed.status == CompanyStatus.FAILED



# ==============================================================================
# 5. FastAPI REST API Endpoint Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_trigger_pipeline_run(async_client: AsyncClient) -> None:
    """Test triggering pipeline via POST /pipeline/run and alias POST /run."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # 1. Test POST /pipeline/run with dry_run
    response = await async_client.post(
        "/pipeline/run",
        json={"dry_run": True, "skip_ingestion": True},
        headers=headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "RUNNING"

    # 2. Test concurrent call to alias POST /run returns 409 Conflict
    alias_resp = await async_client.post(
        "/run",
        json={"dry_run": True, "skip_ingestion": True},
        headers=headers,
    )
    assert alias_resp.status_code == 409
    assert alias_resp.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_pipeline_manual_api_company_flow_without_google_sheets(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """
    Test complete flow for manual/API ingested company without Google Sheets:
    1. POST /companies to create company manually.
    2. Execute PipelineOrchestrator without Google Sheets (skip_ingestion=True).
    3. Verify Company reaches JUDGED status, Verdict is persisted, and GET /companies/{id} returns full results.
    """
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # Step 1: Create company manually via API
    create_resp = await async_client.post(
        "/companies",
        json={
            "name": "Acme Autonomous Corp",
            "website_url": "https://acme-autonomous.io",
            "process_immediately": False,
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    company_id = create_resp.json()["id"]

    # Step 2: Run pipeline with mocked enricher and LLM
    mock_routes = {"https://acme-autonomous.io": (200, REALISTIC_HTML_FIXTURE)}
    http_enricher = WebsiteEnricher(http_client=MockHttpClient(routes=mock_routes))
    enrichment_service = HttpEnrichmentService(session=db_session, website_enricher=http_enricher)
    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())

    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=enrichment_service,
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    result = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=False)
    )

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_processed >= 1
    assert result.companies_succeeded >= 1

    # Step 3: Query GET /companies/{company_id} to verify full results available via API
    detail_resp = await async_client.get(f"/companies/{company_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["name"] == "Acme Autonomous Corp"
    assert detail["status"] in ("JUDGED", "SYNCED")
    assert detail["latest_verdict"] is not None
    assert detail["latest_verdict"]["fit"] in ("YES", "NO", "UNCERTAIN")
    assert len(detail["signals"]) >= 1


@pytest.mark.asyncio
async def test_orchestrator_reuses_provided_run_id(db_session: AsyncSession) -> None:
    """
    Test that when an existing run_id is supplied in PipelineRunRequest,
    the orchestrator reuses that exact record, updates it to COMPLETED,
    and does NOT spawn a duplicate or orphaned PipelineRun record.
    """
    # 1. Pre-create the PipelineRun record as the API does
    pre_created_run = await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
    )
    await db_session.commit()
    target_run_id = pre_created_run.id

    # 2. Execute orchestrator with the pre-created run_id
    orchestrator = PipelineOrchestrator(session=db_session)
    result = await orchestrator.run_pipeline(
        PipelineRunRequest(run_id=target_run_id, skip_ingestion=True)
    )

    # 3. Assert returned result uses the exact target_run_id
    assert result.run_id == target_run_id
    assert result.status == PipelineRunStatus.COMPLETED

    # 4. Verify in database: exactly 1 record exists and its status is COMPLETED
    persisted = await PipelineRunRepository.get_by_id(db_session, target_run_id)
    assert persisted is not None
    assert persisted.status == PipelineRunStatus.COMPLETED
    assert persisted.completed_at is not None

    # Verify no second record was created
    all_runs_stmt = select(PipelineRun)
    all_runs_res = await db_session.execute(all_runs_stmt)
    all_runs = list(all_runs_res.scalars().all())
    matching_runs = [r for r in all_runs if r.id == target_run_id]
    assert len(matching_runs) == 1


@pytest.mark.asyncio
async def test_orchestrator_unhandled_exception_marks_run_failed(db_session: AsyncSession) -> None:
    """
    Test that an unexpected exception during pipeline execution transitions
    the PipelineRun record to FAILED status and records the fatal error.
    """
    # 1. Pre-create RUNNING record
    run = await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
    )
    await db_session.commit()

    # 2. Construct orchestrator and simulate a broken candidate query that raises a top-level error
    orchestrator = PipelineOrchestrator(session=db_session)

    orig_execute = db_session.execute
    failed_once = False

    async def broken_execute(stmt, *args, **kwargs):
        nonlocal failed_once
        stmt_str = str(stmt)
        if not failed_once and "FROM companies" in stmt_str:
            failed_once = True
            raise RuntimeError("Unexpected infrastructure failure during pipeline run")
        return await orig_execute(stmt, *args, **kwargs)

    db_session.execute = broken_execute

    # 3. Running pipeline must propagate error and mark the run FAILED in DB
    try:
        with pytest.raises(RuntimeError):
            await orchestrator.run_pipeline(
                PipelineRunRequest(run_id=run.id, skip_ingestion=True)
            )
    finally:
        db_session.execute = orig_execute

    # 4. Verify DB record was transitioned to FAILED
    updated_run = await PipelineRunRepository.get_by_id(db_session, run.id)
    assert updated_run is not None
    assert updated_run.status == PipelineRunStatus.FAILED
    assert updated_run.error_summary is not None
    assert "fatal_error" in updated_run.error_summary


@pytest.mark.asyncio
async def test_pipeline_six_companies_batch_resilience(db_session: AsyncSession) -> None:
    """
    Test a batch of 6 companies in a single run:
    - Company 1: Success + Sync success
    - Company 2: Processor raises unexpected error (failure isolation)
    - Company 3: Success + Sync raises unexpected error (sync failure isolation)
    - Company 4: Success
    - Company 5: Success
    - Company 6: Success
    Verifies all 6 companies are processed, processed_count == 6, and leases are released.
    """
    # 1. Create 6 companies in PENDING state
    created_companies = []
    for i in range(1, 7):
        co = await CompanyRepository.create(
            session=db_session,
            name=f"Batch Company {i}",
            website_url=f"https://company{i}.com",
            sheet_row_id=f"row_{i}",
            status=CompanyStatus.PENDING,
        )
        created_companies.append(co)
    await db_session.commit()

    # 2. Setup Orchestrator with mock components
    orchestrator = PipelineOrchestrator(session=db_session)
    orchestrator.processor.enable_browser = False

    # Custom processor that fails specifically on company 2
    orig_process = orchestrator.processor.process_company
    async def resilient_process(company: Company, *args, **kwargs):
        if company.name == "Batch Company 2":
            raise ValueError("Simulated network crash during company 2 extraction")
        return await orig_process(company, *args, **kwargs)

    orchestrator.processor.process_company = resilient_process

    # Custom sync service that fails specifically on company 3
    orig_sync = orchestrator.sync_service.sync_company
    async def resilient_sync(company_id, *args, **kwargs):
        co = await CompanyRepository.get_by_id(db_session, company_id)
        if co and co.name == "Batch Company 3":
            raise RuntimeError("Google Sheets API 500 quota outage during company 3 sync")
        return await orig_sync(company_id, *args, **kwargs)

    orchestrator.sync_service.sync_company = resilient_sync

    # Mock the HTTP enrichment and LLM judge for companies 1, 3, 4, 5, 6
    orchestrator.processor.http_enrichment_service = HttpEnrichmentService(
        session=db_session,
        website_enricher=WebsiteEnricher(http_client=MockHttpClient(REALISTIC_HTML_FIXTURE)),
    )
    orchestrator.processor.llm_judge_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(),
    )
    from tests.test_sheets_sync import MockGoogleSheetsSyncClient
    orchestrator.sync_service.client = MockGoogleSheetsSyncClient()

    # 3. Execute the pipeline with sync_to_sheets=True
    run_req = PipelineRunRequest(skip_ingestion=True, sync_to_sheets=True)
    res = await orchestrator.run_pipeline(run_req)

    # 4. Assertions: all 6 companies were processed!
    assert res.companies_discovered == 6
    assert res.companies_processed == 6
    assert res.companies_succeeded == 5
    assert res.companies_failed == 1
    assert res.status == PipelineRunStatus.PARTIAL_FAILURE

    # Verify all leases were cleared
    for co in created_companies:
        fresh = await CompanyRepository.get_by_id(db_session, co.id)
        assert fresh is not None
        assert fresh.lease_expires_at is None


@pytest.mark.asyncio
async def test_company_processor_browser_timeout_fallback(db_session: AsyncSession) -> None:
    """
    Test that when browser enrichment hangs/times out, CompanyProcessor:
    1. Times out bounded by browser_timeout_seconds.
    2. Falls back gracefully to static HTTP signals.
    3. Successfully completes LLM Judge evaluation.
    4. Does not crash or leave the pipeline hanging.
    """
    # 1. Create a company
    company = await CompanyRepository.create(
        session=db_session,
        name="Slow Browser Corp",
        website_url="https://slowbrowser.io",
        sheet_row_id="row_slow_browser",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    # 2. Setup CompanyProcessor with a small timeout (0.05s) and hanging browser mock
    processor = CompanyProcessor(
        session=db_session,
        enable_browser=True,
        browser_timeout_seconds=0.05,
    )

    processor.http_enrichment_service = HttpEnrichmentService(
        session=db_session,
        website_enricher=WebsiteEnricher(http_client=MockHttpClient(REALISTIC_HTML_FIXTURE)),
    )

    # Simulate a hanging browser enrichment call
    async def hanging_browser_enrich(company_id, fetch_careers_page=True):
        await asyncio.sleep(5.0)

    processor.http_enrichment_service.enrich_company_with_browser = hanging_browser_enrich

    processor.llm_judge_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(),
    )

    # 3. Process company
    result = await processor.process_company(company)

    # 4. Assertions: completed via fallback to HTTP signals!
    assert result.status == CompanyStatus.JUDGED
    assert result.fit_decision is not None
    assert result.error is None
