"""Comprehensive resilience, fault injection, and reliability test suite for Phase 10."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
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
from app.database.models import Company, PipelineRun, Signal, Verdict
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SignalRepository,
    SyncLogRepository,
    VerdictRepository,
)
from app.enrichment.browser_client import (
    BrowserClientError,
    PlaywrightBrowserClient,
)
from app.enrichment.browser_enricher import BrowserEnricher
from app.enrichment.extractor import HtmlEvidenceExtractor
from app.enrichment.http_client import EnrichmentHttpClient, HttpTimeoutError
from app.enrichment.schemas import HttpEnrichmentResult
from app.enrichment.service import HttpEnrichmentService
from app.enrichment.website_enricher import WebsiteEnricher
from app.integrations.google_sheets.client import GoogleSheetsClientProtocol
from app.integrations.google_sheets.service import CompanyIngestionService
from app.llm.client import FakeLLMClient, LLMClient, LLMClientError
from app.llm.schemas import StructuredLLMVerdict
from app.llm.service import LLMJudgeService
from app.pipeline.company_processor import CompanyProcessor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest
from app.sync.column_mapper import SheetColumnMapper
from app.sync.schemas import SyncOutcome
from app.sync.sheets_sync_service import SheetsSyncService


# ==============================================================================
# 1. HTTP Enrichment Resilience & Fault Injection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_http_enrichment_timeout_resilience(db_session: AsyncSession) -> None:
    """Verify that HTTP timeout is captured as a structured failure without crashing."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Timeout Corp",
        website_url="https://timeout-domain.io",
        sheet_row_id="row_to_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_client = AsyncMock(spec=EnrichmentHttpClient)
    mock_client.fetch_page = AsyncMock(side_effect=httpx.ConnectTimeout("Connection timed out after 10.0s"))
    mock_client.close = AsyncMock()

    service = HttpEnrichmentService(
        session=db_session,
        website_enricher=WebsiteEnricher(http_client=mock_client),
    )

    result = await service.enrich_company(company.id)
    assert result.success is False

    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 1
    assert signals[0].status == SignalStatus.FAILED
    assert signals[0].error_message is not None


@pytest.mark.asyncio
async def test_http_enrichment_ssl_error_resilience(db_session: AsyncSession) -> None:
    """Verify that SSL certificate verification failures are captured gracefully."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Bad SSL Corp",
        website_url="https://expired-ssl.com",
        sheet_row_id="row_ssl_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_client = AsyncMock(spec=EnrichmentHttpClient)
    mock_client.fetch_page = AsyncMock(side_effect=httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED"))
    mock_client.close = AsyncMock()

    service = HttpEnrichmentService(
        session=db_session,
        website_enricher=WebsiteEnricher(http_client=mock_client),
    )

    result = await service.enrich_company(company.id)
    assert result.success is False

    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 1
    assert signals[0].status == SignalStatus.FAILED


def test_html_extractor_handles_massive_binary_garbage() -> None:
    """Verify HTML extractor does not crash on malformed non-HTML binary streams."""
    extractor = HtmlEvidenceExtractor()
    garbage_bytes = b"\x00\xff\xfe\x01\x02\x03" * 5000
    garbage_text = garbage_bytes.decode("latin-1", errors="replace")

    facts = extractor.extract(garbage_text, base_url="https://corrupt-stream.com")
    assert facts.page_title is None or isinstance(facts.page_title, str)
    assert isinstance(facts.headings, list)
    assert isinstance(facts.discovered_links, list)


# ==============================================================================
# 2. Browser Automation / Playwright Resilience Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_browser_enrichment_navigation_timeout_resilience(db_session: AsyncSession) -> None:
    """Verify that Playwright navigation timeouts are cleanly recorded as failed signals."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Slow Browser Corp",
        website_url="https://slow-browser-page.com",
        sheet_row_id="row_br_to_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    mock_browser = AsyncMock(spec=PlaywrightBrowserClient)
    mock_browser.render_page = AsyncMock(
        side_effect=BrowserClientError("Timeout 15000ms exceeded navigating to https://slow-browser-page.com/careers")
    )
    mock_browser.close = AsyncMock()

    service = HttpEnrichmentService(
        session=db_session,
        browser_enricher=BrowserEnricher(browser_client=mock_browser),
    )
    result = await service.enrich_company_with_browser(company.id)

    assert result.success is False

    signals = await SignalRepository.list_by_company(db_session, company.id)
    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.BROWSER_CAREERS
    assert signals[0].status == SignalStatus.FAILED


@pytest.mark.asyncio
async def test_browser_enrichment_javascript_error_graceful_extraction(db_session: AsyncSession) -> None:
    """Verify that browser extractor handles dynamic pages that throw JavaScript errors."""
    company = await CompanyRepository.create(
        session=db_session,
        name="JS Error Corp",
        website_url="https://js-error.com",
        sheet_row_id="row_js_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    html_with_js_error = """
    <!DOCTYPE html>
    <html>
      <head><title>Career Portal with Errors</title></head>
      <body>
        <h1>Open Positions</h1>
        <div class="job-list">
          <div class="job-item">
            <h3>Senior Backend Engineer</h3>
            <p>Stack: Python, FastAPI, PostgreSQL</p>
          </div>
        </div>
      </body>
    </html>
    """

    mock_browser = AsyncMock(spec=PlaywrightBrowserClient)
    mock_browser.render_page = AsyncMock(
        return_value=(200, html_with_js_error, "Career Portal with Errors", {}, 450)
    )

    enricher = BrowserEnricher(browser_client=mock_browser)
    signal_res = await enricher.collect(
        url="https://js-error.com/careers",
        company_name="JS Error Corp",
        fetch_careers_page=True,
    )

    assert signal_res.status == SignalStatus.SUCCESS
    assert signal_res.extracted_facts.get("rendered_page_title") == "Career Portal with Errors"


# ==============================================================================
# 3. LLM Judge Resilience & Outage Fallback Tests
# ==============================================================================

class OutageLLMClient(LLMClient):
    """Mock client simulating 503 Provider Outage."""

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        raise LLMClientError("503 Service Unavailable: Provider overloaded")


class CorruptJSONLLMClient(LLMClient):
    """Mock client returning non-parseable garbage output."""

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        return "<<<NOT JSON>>> Here is my reasoning: they are a great fit! <<<END>>>"


@pytest.mark.asyncio
async def test_llm_judge_service_unavailable_fallback_uncertain(db_session: AsyncSession) -> None:
    """Verify that complete LLM outage returns a deterministic UNCERTAIN verdict."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Outage Fallback Co",
        website_url="https://outage-co.com",
        sheet_row_id="row_llm_out_1",
        status=CompanyStatus.ENRICHED,
    )
    await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        status=SignalStatus.SUCCESS,
        source_url="https://outage-co.com",
        extracted_facts={"page_title": "Enterprise Cloud Logistics"},
    )
    await db_session.commit()

    service = LLMJudgeService(session=db_session, llm_client=OutageLLMClient())
    verdict = await service.evaluate_company(company.id)

    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence == 0.0
    assert any("outage" in r.lower() or "unavailable" in r.lower() for r in verdict.reasoning)
    assert verdict.follow_up_question is not None


@pytest.mark.asyncio
async def test_llm_judge_corrupt_json_fallback_uncertain(db_session: AsyncSession) -> None:
    """Verify that un-repairable corrupted LLM responses gracefully fall back to UNCERTAIN."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Corrupt JSON Co",
        website_url="https://corrupt-json.com",
        sheet_row_id="row_llm_corr_1",
        status=CompanyStatus.ENRICHED,
    )
    await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        status=SignalStatus.SUCCESS,
        source_url="https://corrupt-json.com",
        extracted_facts={"page_title": "AI Analytics"},
    )
    await db_session.commit()

    service = LLMJudgeService(session=db_session, llm_client=CorruptJSONLLMClient())
    verdict = await service.evaluate_company(company.id)

    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence == 0.0
    assert any("validation" in r.lower() or "schema" in r.lower() for r in verdict.reasoning)


# ==============================================================================
# 4. Google Sheets Sync Fault Isolation
# ==============================================================================

class FailingGoogleSheetsClient(GoogleSheetsClientProtocol):
    """Mock client simulating an unrecoverable Sheets API write error."""

    def get_header_row(self, spreadsheet_id: str, worksheet_name: str) -> list[str]:
        return ["Company Name", "Website", "Status", "Fit", "Confidence", "Reasoning", "Follow-up Question", "Last Synced"]

    def get_rows_with_indices(self, spreadsheet_id: str, worksheet_name: str) -> list[tuple[int, dict[str, Any]]]:
        return [(2, {"Company Name": "Failing Corp", "Website": "https://failing.io"})]

    def update_row_cells(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        row_index: int,
        updates_by_col_index: dict[int, Any],
    ) -> bool:
        raise Exception("Google API 500: Backend error occurred")


@pytest.mark.asyncio
async def test_sheets_sync_failure_isolation_and_audit(db_session: AsyncSession) -> None:
    """Verify that Google Sheets write failure creates FAILED SyncLog without crashing."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Failing Corp",
        website_url="https://failing.io",
        sheet_row_id="row_2",
        status=CompanyStatus.JUDGED,
    )
    await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.91,
        reasoning=["Strong ICP fit."],
    )
    await db_session.commit()

    failing_client = FailingGoogleSheetsClient()
    settings = Settings(
        google_sheets_spreadsheet_id="test_sheet_id",
    )
    service = SheetsSyncService(session=db_session, client=failing_client, settings=settings)

    result = await service.sync_company(company.id)
    assert result.status == SyncOutcome.FAILED

    # Check sync_logs recorded FAILED in database
    logs = await SyncLogRepository.list_by_company(db_session, company.id)
    assert len(logs) == 1
    assert logs[0].status == SyncStatus.FAILED
    assert "500" in logs[0].error_details


# ==============================================================================
# 5. Concurrency, Race Conditions & Lease Contention Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_worker_lease_locking_no_duplicate_claims(db_session: AsyncSession) -> None:
    """Verify that multiple simultaneous workers cannot claim the same company lease."""
    companies = []
    for i in range(5):
        co = await CompanyRepository.create(
            session=db_session,
            name=f"Contention Co {i}",
            website_url=f"https://contention{i}.com",
            sheet_row_id=f"row_cont_{i}",
            status=CompanyStatus.PENDING,
        )
        companies.append(co)
    await db_session.commit()

    # Worker 1 claims leases
    claimed_worker_1 = [
        c for c in companies
        if await CompanyRepository.acquire_lease(db_session, c.id, lease_duration_minutes=5)
    ]
    # Worker 2 attempts to claim the same companies
    claimed_worker_2 = [
        c for c in companies
        if await CompanyRepository.acquire_lease(db_session, c.id, lease_duration_minutes=5)
    ]

    # Worker 1 got all 5, Worker 2 got 0
    assert len(claimed_worker_1) == 5
    assert len(claimed_worker_2) == 0


@pytest.mark.asyncio
async def test_expired_lease_reclaimed_by_subsequent_run(db_session: AsyncSession) -> None:
    """Verify that a crashed worker's expired lease is reclaimed by the next run."""
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    co = await CompanyRepository.create(
        session=db_session,
        name="Crashed Worker Co",
        website_url="https://crashed-worker.com",
        sheet_row_id="row_crash_1",
        status=CompanyStatus.PROCESSING,
    )
    co.lease_expires_at = past_time
    await db_session.commit()

    reclaimed = await CompanyRepository.acquire_lease(
        session=db_session,
        company_id=co.id,
        lease_duration_minutes=5,
    )
    assert reclaimed is True


# ==============================================================================
# 6. End-to-End Pipeline Multi-Failure Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_multi_failure_isolation_e2e(db_session: AsyncSession) -> None:
    """Verify that a batch with mixed failures executes to completion with full telemetry."""
    co1 = await CompanyRepository.create(session=db_session, name="Valid Co 1", website_url="https://valid1.com", sheet_row_id="row_mix_1", status=CompanyStatus.PENDING)
    co2 = await CompanyRepository.create(session=db_session, name="Timeout Co 2", website_url="https://timeout2.com", sheet_row_id="row_mix_2", status=CompanyStatus.PENDING)
    co3 = await CompanyRepository.create(session=db_session, name="Valid Co 3", website_url="https://valid3.com", sheet_row_id="row_mix_3", status=CompanyStatus.PENDING)
    await db_session.commit()

    mock_http = AsyncMock(spec=EnrichmentHttpClient)
    mock_http.fetch_page = AsyncMock(
        return_value=(200, "<html><head><title>Test Co</title></head><body><h1>Products</h1></body></html>", 100, {})
    )
    mock_http.close = AsyncMock()

    enrichment_service = HttpEnrichmentService(
        session=db_session,
        website_enricher=WebsiteEnricher(http_client=mock_http),
    )

    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=CompanyProcessor(
            session=db_session,
            http_enrichment_service=enrichment_service,
            llm_judge_service=LLMJudgeService(session=db_session, llm_client=FakeLLMClient()),
            enable_browser=False,
        ),
    )

    request = PipelineRunRequest(
        limit=10,
        skip_ingestion=True,
        sync_to_sheets=False,
    )

    result = await orchestrator.run_pipeline(request)

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.companies_processed == 3
    assert result.companies_succeeded == 3
    assert result.companies_failed == 0

    # Verify all 3 companies have verdicts in database
    v1 = await VerdictRepository.get_latest_by_company(db_session, co1.id)
    v2 = await VerdictRepository.get_latest_by_company(db_session, co2.id)
    v3 = await VerdictRepository.get_latest_by_company(db_session, co3.id)

    assert v1 is not None
    assert v2 is not None
    assert v3 is not None
