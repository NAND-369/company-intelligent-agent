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

    # Second Run (Company already JUDGED)
    res2 = await orchestrator.run_pipeline(PipelineRunRequest(skip_ingestion=True))
    assert res2.companies_discovered == 0  # No PENDING / ENRICHED companies remaining

    # Signals and verdicts should NOT be duplicated
    signals = await SignalRepository.list_by_company(db_session, co.id)
    assert len(signals) == 1
    verdicts = await VerdictRepository.list_by_company(db_session, co.id)
    assert len(verdicts) == 1


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
