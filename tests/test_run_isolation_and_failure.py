"""Comprehensive tests for pipeline run isolation, failure cleanup, and stale lease recovery."""

from datetime import datetime, timedelta, timezone
import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SignalStatus,
    SignalType,
    TriggerType,
)
from app.database.models import Company, Signal, Verdict
from app.database.repositories import (
    CompanyRepository,
    PipelineRunRepository,
    SignalRepository,
    VerdictRepository,
)
from app.enrichment.schemas import HttpEnrichmentResult, NormalizedSignalResult
from app.enrichment.service import HttpEnrichmentService
from app.llm.client import LLMClient, LLMClientError
from app.llm.parser import LLMParseError
from app.llm.service import LLMJudgeService
from app.pipeline.company_processor import CompanyProcessor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.schemas import PipelineRunRequest


class FakeLLMClient(LLMClient):
    """Configurable mock LLM client for testing specific success/failure branches."""

    def __init__(
        self,
        default_verdict: str = "YES",
        raise_error: Exception | None = None,
        custom_response: str | None = None,
    ) -> None:
        self.default_verdict = default_verdict
        self.raise_error = raise_error
        self.custom_response = custom_response

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        if self.raise_error:
            raise self.raise_error
        if self.custom_response:
            return self.custom_response
        return json.dumps({
            "fit": self.default_verdict,
            "confidence": 0.92,
            "confidence_rationale": "Strong evidence matching rubric.",
            "reasoning": ["Clear B2B software offerings."],
            "follow_up_question": None,
            "key_signals_used": ["HTTP_WEBSITE"],
        })


class MockHttpEnrichmentService:
    """Mock enrichment service that adds a standard signal."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enrich_company(self, company_id: uuid.UUID, **kwargs) -> HttpEnrichmentResult:
        sig = await SignalRepository.create(
            session=self.session,
            company_id=company_id,
            signal_type=SignalType.HTTP_WEBSITE,
            source_url="https://example.com",
            extracted_facts={"page_title": "B2B Cloud Services"},
            status=SignalStatus.SUCCESS,
        )
        await CompanyRepository.update_status(self.session, company_id, CompanyStatus.ENRICHED)
        await self.session.commit()
        return HttpEnrichmentResult(company_id=company_id, success=True, signals_collected=[])

    async def enrich_company_with_browser(self, company_id: uuid.UUID, **kwargs) -> HttpEnrichmentResult:
        return await self.enrich_company(company_id, **kwargs)


# ==============================================================================
# 1. Gemini Success -> Company + Verdict Persisted
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_success_persists_company_and_verdict(db_session: AsyncSession) -> None:
    """Verify that a successful Gemini evaluation persists Company as JUDGED and saves Verdict."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Alpha Tech",
        website_url="https://alphatech.com",
        sheet_row_id="row_success_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient(default_verdict="YES"))
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )

    res = await processor.process_company(company)

    assert res.status == CompanyStatus.JUDGED
    assert res.fit_decision == FitDecision.YES
    assert res.confidence == 0.92

    # Verify database state
    verdict = await VerdictRepository.get_latest_by_company(db_session, company.id)
    assert verdict is not None
    assert verdict.fit == FitDecision.YES
    assert verdict.confidence == 0.92


# ==============================================================================
# 2. Gemini Returns Valid UNCERTAIN -> Company + Verdict Persisted
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_valid_uncertain_persisted(db_session: AsyncSession) -> None:
    """Verify that an authentic UNCERTAIN decision from Gemini is persisted as a valid verdict."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Ambiguous Logistics",
        website_url="https://ambiguous.com",
        sheet_row_id="row_uncertain_1",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    valid_uncertain_json = json.dumps({
        "fit": "UNCERTAIN",
        "confidence": 0.25,
        "confidence_rationale": "Evidence mentions both consumer and business offerings without clarity.",
        "reasoning": ["Limited public information on enterprise tier."],
        "follow_up_question": "Does the company sell directly to enterprise accounts?",
        "key_signals_used": ["HTTP_WEBSITE"],
    })

    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient(custom_response=valid_uncertain_json))
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )

    res = await processor.process_company(company)

    assert res.status == CompanyStatus.JUDGED
    assert res.fit_decision == FitDecision.UNCERTAIN
    assert res.confidence == 0.25

    verdict = await VerdictRepository.get_latest_by_company(db_session, company.id)
    assert verdict is not None
    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence == 0.25
    assert verdict.follow_up_question == "Does the company sell directly to enterprise accounts?"


# ==============================================================================
# 3. Gemini 429 Rate Limit -> No Misleading Verdict / State Cleaned Up
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_429_cleans_up_state_and_no_verdict(db_session: AsyncSession) -> None:
    """Verify that a 429 rate limit error deletes company and leaves zero misleading records in PostgreSQL."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Rate Limited Corp",
        website_url="https://ratelimited.com",
        sheet_row_id="row_429_1",
        status=CompanyStatus.PENDING,
    )
    company_id = company.id
    await db_session.commit()

    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(raise_error=LLMClientError("429 Resource Exhausted / Rate limit exceeded")),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )

    res = await processor.process_company(company)

    assert res.status == CompanyStatus.FAILED
    assert "429" in (res.error or "")

    # Verify company was deleted from PostgreSQL
    reloaded = await CompanyRepository.get_by_id(db_session, company_id)
    assert reloaded is None

    # Verify no verdict was saved
    verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert verdict is None

    # Verify signals were cleaned up
    signals = await SignalRepository.list_by_company(db_session, company_id)
    assert len(signals) == 0


# ==============================================================================
# 4. Gemini Timeout -> Cleanup / Deletion
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_timeout_cleans_up_state(db_session: AsyncSession) -> None:
    """Verify that an LLM timeout triggers rollback and deletes the company from PostgreSQL."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Timeout Corp",
        website_url="https://timeout-co.com",
        sheet_row_id="row_timeout_1",
        status=CompanyStatus.PENDING,
    )
    company_id = company.id
    await db_session.commit()

    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(raise_error=TimeoutError("Request to Gemini API timed out after 30s")),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )

    res = await processor.process_company(company)

    assert res.status == CompanyStatus.FAILED
    # Verify company was completely deleted from PostgreSQL
    reloaded = await CompanyRepository.get_by_id(db_session, company_id)
    assert reloaded is None

    verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert verdict is None


# ==============================================================================
# 5. Gemini Malformed JSON -> Cleanup / Deletion
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_malformed_json_cleans_up_state(db_session: AsyncSession) -> None:
    """Verify that un-repairable corrupted JSON output deletes the company from PostgreSQL."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Malformed JSON Corp",
        website_url="https://malformed.com",
        sheet_row_id="row_malformed_1",
        status=CompanyStatus.PENDING,
    )
    company_id = company.id
    await db_session.commit()

    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(custom_response="<<<INVALID NOT JSON RESPONSE>>>"),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )

    res = await processor.process_company(company)

    assert res.status == CompanyStatus.FAILED
    # Verify company was completely deleted from PostgreSQL
    reloaded = await CompanyRepository.get_by_id(db_session, company_id)
    assert reloaded is None

    verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert verdict is None


# ==============================================================================
# 6. Multi-Company Run with Mixed Success/Failure -> Only Successful in Results
# ==============================================================================

@pytest.mark.asyncio
async def test_multi_company_run_mixed_success_failure(db_session: AsyncSession) -> None:
    """Verify that multi-company run with mixed outcomes isolates failures and retains only valid results."""
    co_a = await CompanyRepository.create(db_session, "Company A", "https://co-a.com", sheet_row_id="row_mix_a")
    co_b = await CompanyRepository.create(db_session, "Company B", "https://co-b.com", sheet_row_id="row_mix_b")
    co_c = await CompanyRepository.create(db_session, "Company C", "https://co-c.com", sheet_row_id="row_mix_c")
    co_d = await CompanyRepository.create(db_session, "Company D", "https://co-d.com", sheet_row_id="row_mix_d")
    co_a_id = co_a.id
    co_b_id = co_b.id
    co_c_id = co_c.id
    co_d_id = co_d.id
    await db_session.commit()

    class MixedLLMClient(LLMClient):
        async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
            if "Company B" in user_prompt:
                raise LLMClientError("429 Rate Limit on Company B")
            if "Company D" in user_prompt or "CORRUPT JSON OUTPUT" in user_prompt:
                return "CORRUPT JSON OUTPUT"
            return json.dumps({
                "fit": "YES",
                "confidence": 0.90,
                "confidence_rationale": "Enterprise B2B match.",
                "reasoning": ["Matches rubric criteria."],
            })

    llm_service = LLMJudgeService(session=db_session, llm_client=MixedLLMClient())
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=False)
    )

    assert run_result.companies_discovered == 4
    assert run_result.companies_processed == 4
    assert run_result.companies_succeeded == 2
    assert run_result.companies_failed == 2

    # Check database: Company A and C exist with verdicts
    co_a_db = await CompanyRepository.get_by_id(db_session, co_a_id)
    co_c_db = await CompanyRepository.get_by_id(db_session, co_c_id)
    assert co_a_db is not None and co_a_db.status == CompanyStatus.JUDGED
    assert co_c_db is not None and co_c_db.status == CompanyStatus.JUDGED

    verdict_a = await VerdictRepository.get_latest_by_company(db_session, co_a_id)
    verdict_c = await VerdictRepository.get_latest_by_company(db_session, co_c_id)
    assert verdict_a is not None and verdict_a.fit == FitDecision.YES
    assert verdict_c is not None and verdict_c.fit == FitDecision.YES

    # Check database: Failed Company B and D were deleted completely
    co_b_db = await CompanyRepository.get_by_id(db_session, co_b_id)
    co_d_db = await CompanyRepository.get_by_id(db_session, co_d_id)
    assert co_b_db is None
    assert co_d_db is None

    verdict_b = await VerdictRepository.get_latest_by_company(db_session, co_b_id)
    verdict_d = await VerdictRepository.get_latest_by_company(db_session, co_d_id)
    assert verdict_b is None
    assert verdict_d is None

    # Normal company listing returns only successful companies
    companies, total = await CompanyRepository.list_companies(db_session)
    assert total == 2
    assert {c.name for c in companies} == {"Company A", "Company C"}


# ==============================================================================
# 7. Latest-Run API Returns Run-Specific Companies
# ==============================================================================

@pytest.mark.asyncio
async def test_latest_run_telemetry_returns_run_specific_companies(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify that GET /runs/{run_id} returns company_results specific to that run."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # Create 1 company
    co = await CompanyRepository.create(db_session, "Target Co", "https://target.com", sheet_row_id="row_telemetry_1")
    await db_session.commit()

    run = await PipelineRunRepository.create(
        session=db_session,
        trigger_type=TriggerType.ON_DEMAND_API,
        status=PipelineRunStatus.RUNNING,
    )
    run_id = run.id
    # Save completed run with metadata
    await PipelineRunRepository.complete_run(
        session=db_session,
        run_id=run_id,
        status=PipelineRunStatus.COMPLETED,
        error_summary={
            "errors": [],
            "company_results": [
                {
                    "company_id": str(co.id),
                    "company_name": "Target Co",
                    "website_url": "https://target.com",
                    "status": "JUDGED",
                    "fit": "YES",
                    "confidence": 0.95,
                    "reasoning": ["Matches criteria."],
                    "is_synced": True,
                }
            ],
        },
    )
    await db_session.commit()

    resp = await async_client.get(f"/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "company_results" in data
    assert len(data["company_results"]) == 1
    assert data["company_results"][0]["company_name"] == "Target Co"
    assert data["company_results"][0]["fit"] == "YES"


# ==============================================================================
# 8. Zero-Company Run Completes Cleanly with Zero Results
# ==============================================================================

@pytest.mark.asyncio
async def test_zero_company_run_behavior(db_session: AsyncSession) -> None:
    """Verify that when 0 eligible companies exist, the pipeline completes with 0 results."""
    orchestrator = PipelineOrchestrator(session=db_session)
    res = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=False, force_reprocess=False)
    )

    assert res.status == PipelineRunStatus.COMPLETED
    assert res.companies_discovered == 0
    assert res.companies_processed == 0
    assert res.companies_succeeded == 0
    assert len(res.company_results) == 0


# ==============================================================================
# 9. Stale PROCESSING Company is Recoverable
# ==============================================================================

@pytest.mark.asyncio
async def test_stale_processing_company_recovered_by_pipeline(db_session: AsyncSession) -> None:
    """Verify that a company stuck in PROCESSING with an expired lease is discovered and processed."""
    past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    stuck_co = await CompanyRepository.create(
        session=db_session,
        name="Stuck Co (Atlassian scenario)",
        website_url="https://stuck-co.com",
        sheet_row_id="row_stale_1",
        status=CompanyStatus.PROCESSING,
    )
    stuck_co.lease_expires_at = past_time
    await db_session.commit()

    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient(default_verdict="YES"))
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(skip_ingestion=True, sync_to_sheets=False, force_reprocess=False)
    )

    assert run_result.companies_discovered == 1
    assert run_result.companies_succeeded == 1

    reloaded = await CompanyRepository.get_by_id(db_session, stuck_co.id)
    assert reloaded is not None
    assert reloaded.status == CompanyStatus.JUDGED
    assert reloaded.lease_expires_at is None


# ==============================================================================
# 10. Dashboard Initial State & No Historical Results in HTML
# ==============================================================================

@pytest.mark.asyncio
async def test_landing_page_html_starts_with_empty_companies_and_no_historical_section(
    async_client: AsyncClient,
) -> None:
    """Verify that the landing page starts with an empty working list and contains no historical section."""
    resp = await async_client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # Verify initial table message
    assert "No companies added yet." in html

    # Verify 05.B / HISTORICAL RESULTS section is completely removed
    assert "HISTORICAL RESULTS" not in html
    assert "05.B / ARCHIVE" not in html
    assert "renderHistoricalVerdicts" not in html
    assert "loadCompanies()" not in html

    # Verify no master API key / localStorage handling exists in HTML
    assert "agent_api_key" not in html
    assert "promptApiKey" not in html
    assert "localStorage" not in html



# ==============================================================================
# 11. Pipeline Scoped Exclusively to Explicit Company IDs
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_run_scoped_to_explicit_company_ids(db_session: AsyncSession) -> None:
    """Verify that when company_ids is passed, only those specific companies are evaluated."""
    # Pre-existing database companies that should NOT be touched
    old_co1 = await CompanyRepository.create(db_session, "Old Co 1", "https://old1.com")
    old_co2 = await CompanyRepository.create(db_session, "Old Co 2", "https://old2.com")
    old_co3 = await CompanyRepository.create(db_session, "Old Co 3", "https://old3.com")

    # Newly added session companies
    datadog = await CompanyRepository.create(db_session, "Datadog", "https://datadoghq.com")
    atlassian = await CompanyRepository.create(db_session, "Atlassian", "https://atlassian.com")
    await db_session.commit()

    llm_service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient(default_verdict="YES"))
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(session=db_session, processor=processor)

    # Trigger run scoped ONLY to Datadog and Atlassian
    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[datadog.id, atlassian.id],
            skip_ingestion=True,
            sync_to_sheets=False,
        )
    )

    assert run_result.companies_discovered == 2
    assert run_result.companies_processed == 2
    assert run_result.companies_succeeded == 2
    assert {r.company_name for r in run_result.company_results} == {"Datadog", "Atlassian"}

    # Verify old companies were NOT evaluated and remain PENDING
    fresh_old1 = await CompanyRepository.get_by_id(db_session, old_co1.id)
    fresh_old2 = await CompanyRepository.get_by_id(db_session, old_co2.id)
    fresh_old3 = await CompanyRepository.get_by_id(db_session, old_co3.id)
    assert fresh_old1.status == CompanyStatus.PENDING
    assert fresh_old2.status == CompanyStatus.PENDING
    assert fresh_old3.status == CompanyStatus.PENDING


# ==============================================================================
# 12. Pipeline Run with Empty company_ids Processes Zero
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_run_empty_company_ids_processes_zero(db_session: AsyncSession) -> None:
    """Verify that triggering a run with company_ids=[] processes 0 companies without touching DB records."""
    await CompanyRepository.create(db_session, "Pre-existing 1", "https://pre1.com")
    await CompanyRepository.create(db_session, "Pre-existing 2", "https://pre2.com")
    await db_session.commit()

    orchestrator = PipelineOrchestrator(session=db_session)
    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[],
            skip_ingestion=True,
            sync_to_sheets=False,
        )
    )

    assert run_result.companies_discovered == 0
    assert run_result.companies_processed == 0
    assert len(run_result.company_results) == 0


# ==============================================================================
# 13. Add Company API Success and Duplicate Feedback
# ==============================================================================

@pytest.mark.asyncio
async def test_api_add_company_success_and_duplicate_conflict(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify that POST /companies succeeds on new company and returns 409 Conflict on duplicate."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # 1. Add Datadog -> Success
    res1 = await async_client.post(
        "/companies",
        json={"name": "Datadog", "website_url": "https://datadoghq.com"},
        headers=headers,
    )
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["name"] == "Datadog"
    assert data1["status"] == "PENDING"

    # 2. Add Atlassian -> Success
    res2 = await async_client.post(
        "/companies",
        json={"name": "Atlassian", "website_url": "https://atlassian.com"},
        headers=headers,
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["name"] == "Atlassian"

    # 3. Add Duplicate Datadog -> 409 Conflict with structured details
    res3 = await async_client.post(
        "/companies",
        json={"name": "Datadog", "website_url": "https://datadoghq.com"},
        headers=headers,
    )
    assert res3.status_code == 409
    res3_data = res3.json()
    err_msg = res3_data.get("error", {}).get("message") or res3_data.get("detail", "")
    assert "already exists" in err_msg
    details = res3_data.get("error", {}).get("details")
    assert details is not None
    assert details["duplicate"] is True
    assert details["company_id"] == data1["id"]
    assert details["has_result"] is False


# ==============================================================================
# 14. Duplicate Company with Existing Verdict Exposes has_result=True
# ==============================================================================

@pytest.mark.asyncio
async def test_api_duplicate_company_with_existing_verdict(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify duplicate returns has_result=True and latest verdict summary when evaluated."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # 1. Create and evaluate company
    company = await CompanyRepository.create(
        session=db_session,
        name="Sarvam AI",
        website_url="https://www.sarvam.ai",
        status=CompanyStatus.JUDGED,
    )
    verdict = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.95,
        confidence_rationale="B2B AI developer platform",
        reasoning=["Direct REST APIs and SDK for enterprise developers."],
    )
    await db_session.commit()

    # 2. Attempt duplicate add
    res = await async_client.post(
        "/companies",
        json={"name": "Sarvam AI", "website_url": "https://www.sarvam.ai"},
        headers=headers,
    )
    assert res.status_code == 409
    data = res.json()
    details = data["error"]["details"]
    assert details["duplicate"] is True
    assert details["company_id"] == str(company.id)
    assert details["has_result"] is True
    assert details["latest_verdict"]["fit"] == "YES"
    assert details["latest_verdict"]["confidence"] == 0.95


# ==============================================================================
# 15. View Existing Result Endpoint
# ==============================================================================

@pytest.mark.asyncio
async def test_view_existing_result_endpoint(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify GET /companies/{id} returns company details, latest verdict, and signals."""
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    company = await CompanyRepository.create(
        session=db_session,
        name="Stripe",
        website_url="https://stripe.com",
        status=CompanyStatus.JUDGED,
    )
    verdict = await VerdictRepository.create(
        session=db_session,
        company_id=company.id,
        fit=FitDecision.YES,
        confidence=0.98,
        confidence_rationale="Developer payments API infrastructure",
        reasoning=["Developer-first financial infrastructure."],
    )
    await db_session.commit()

    res = await async_client.get(f"/companies/{company.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(company.id)
    assert data["name"] == "Stripe"
    assert data["latest_verdict"]["fit"] == "YES"
    assert data["latest_verdict"]["confidence"] == 0.98


# ==============================================================================
# 16. Recompute Existing Company Reuses UUID and Updates Verdict
# ==============================================================================

@pytest.mark.asyncio
async def test_recompute_existing_company_reuses_uuid(db_session: AsyncSession) -> None:
    """Verify recomputing an existing company reuses its UUID without creating duplicate DB rows."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Datadog",
        website_url="https://datadoghq.com",
        status=CompanyStatus.PENDING,
    )
    original_id = company.id
    await db_session.commit()

    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(default_verdict="YES"),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    # Recompute with explicit company ID and force_reprocess=True
    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[original_id],
            skip_ingestion=True,
            sync_to_sheets=False,
            force_reprocess=True,
        )
    )

    assert run_result.companies_processed == 1
    assert run_result.companies_succeeded == 1
    assert run_result.company_results[0].company_id == original_id
    assert run_result.company_results[0].fit_decision == FitDecision.YES

    # Verify no duplicate company row created
    from sqlalchemy import select, func
    count = await db_session.scalar(select(func.count()).select_from(Company).where(Company.name == "Datadog"))
    assert count == 1


# ==============================================================================
# 17. New Company Technical Failure Cleans Up Without Fake UNCERTAIN
# ==============================================================================

@pytest.mark.asyncio
async def test_new_company_technical_failure_cleans_up_without_fake_uncertain(db_session: AsyncSession) -> None:
    """Verify that if Gemini encounters a technical 429 on a new company, it is cleanly removed."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Rate Limited Co",
        website_url="https://ratelimit.com",
        status=CompanyStatus.PENDING,
    )
    company_id = company.id
    await db_session.commit()

    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(raise_error=LLMClientError("Gemini API rate limit 429")),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[company_id],
            skip_ingestion=True,
            sync_to_sheets=False,
            force_reprocess=False,
        )
    )

    assert run_result.companies_failed >= 1
    # Verify new company is deleted and no fake verdict persists
    reloaded = await CompanyRepository.get_by_id(db_session, company_id)
    assert reloaded is None
    verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert verdict is None


# ==============================================================================
# 18. Existing Company Recompute Failure Preserves Company and Previous Verdict
# ==============================================================================

@pytest.mark.asyncio
async def test_existing_company_recompute_failure_preserves_company_and_previous_verdict(
    db_session: AsyncSession,
) -> None:
    """Verify that transient Gemini 429 during recompute preserves the existing Company row and prior verdict."""
    # 1. Create an existing company with a valid previous verdict
    company = await CompanyRepository.create(
        session=db_session,
        name="Sarvam AI",
        website_url="https://www.sarvam.ai",
        status=CompanyStatus.JUDGED,
    )
    company_id = company.id
    prior_verdict = await VerdictRepository.create(
        session=db_session,
        company_id=company_id,
        fit=FitDecision.YES,
        confidence=0.95,
        confidence_rationale="B2B AI developer platform",
        reasoning=["Direct REST APIs and SDK for enterprise developers."],
    )
    await db_session.commit()

    # 2. Recompute with simulated Gemini 429 / timeout failure
    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(raise_error=LLMClientError("Gemini API rate limit 429 (ResourceExhausted)")),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[company_id],
            skip_ingestion=True,
            sync_to_sheets=False,
            force_reprocess=True,
        )
    )

    # 3. Assert failure is reported in run telemetry
    assert run_result.companies_failed == 1
    assert run_result.company_results[0].status == CompanyStatus.FAILED
    assert "429" in (run_result.company_results[0].error or "")

    # 4. Verify existing Company row is PRESERVED in PostgreSQL
    preserved_company = await CompanyRepository.get_by_id(db_session, company_id)
    assert preserved_company is not None
    assert preserved_company.id == company_id
    assert preserved_company.name == "Sarvam AI"

    # 5. Verify previous valid verdict is PRESERVED and NOT replaced with fake UNCERTAIN
    current_verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert current_verdict is not None
    assert current_verdict.id == prior_verdict.id
    assert current_verdict.fit == FitDecision.YES
    assert current_verdict.confidence == 0.95

    # 6. Verify no duplicate Company rows created
    from sqlalchemy import select, func
    count = await db_session.scalar(select(func.count()).select_from(Company).where(Company.name == "Sarvam AI"))
    assert count == 1


# ==============================================================================
# 16. Stale/Invalid Verdict Ingestion and Re-evaluation Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_stale_invalid_uncertain_verdict_is_overwritten_by_b2c_evaluation(db_session: AsyncSession) -> None:
    """
    Verify that:
    1. A legacy invalid verdict (UNCERTAIN 0.95) in DB is NOT reused or preserved.
    2. Processing with B2C signals correctly generates and persists NO with high confidence.
    3. Run telemetry company_results reflects the newly evaluated NO verdict from the active run.
    """
    from sqlalchemy import text
    from app.database.models import Verdict

    # 1. Create company in DB
    company = await CompanyRepository.create(
        session=db_session,
        name="Myntra Fashion",
        website_url="https://www.myntra.com",
        sheet_row_id="row_myntra_legacy",
        status=CompanyStatus.JUDGED,
    )
    company_id = company.id
    await db_session.commit()

    # 2. Directly insert raw legacy invalid verdict bypassing ORM validation to simulate pre-migration DB state
    from sqlalchemy import insert
    stale_verdict_id = uuid.uuid4()
    await db_session.execute(
        insert(Verdict.__table__).values(
            id=stale_verdict_id,
            company_id=company_id,
            fit=FitDecision.UNCERTAIN,
            confidence=0.95,
            reasoning=["Legacy pre-validation verdict"],
            evaluated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    # Verify stale verdict exists
    stale_record = await db_session.get(Verdict, stale_verdict_id)
    assert stale_record is not None
    assert stale_record.fit == FitDecision.UNCERTAIN
    assert stale_record.confidence == 0.95

    # 3. Add B2C consumer signals
    await SignalRepository.create(
        session=db_session,
        company_id=company_id,
        signal_type=SignalType.HTTP_WEBSITE,
        source_url="https://www.myntra.com",
        extracted_facts={
            "page_title": "Online Shopping for Women, Men, Kids Fashion & Lifestyle - Myntra",
            "headings_summary": ["Trending in Indian Wear", "Top Brands & Discounts", "Myntra Insider Rewards"],
            "main_content_snippet": "Myntra is India's premier consumer fashion and e-commerce shopping platform.",
        },
    )
    await db_session.commit()

    # 4. Run pipeline on the company (force_reprocess=True to reprocess existing company)
    from app.llm.client import FakeLLMClient as AppFakeLLMClient
    llm_service = LLMJudgeService(session=db_session, llm_client=AppFakeLLMClient())
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[company_id],
            skip_ingestion=True,
            sync_to_sheets=False,
            force_reprocess=True,
        )
    )

    # 5. Assert run telemetry
    assert run_result.companies_processed == 1
    assert run_result.companies_succeeded == 1
    assert len(run_result.company_results) == 1

    co_result = run_result.company_results[0]
    assert co_result.status == CompanyStatus.JUDGED
    assert co_result.fit_decision == FitDecision.NO
    assert co_result.confidence >= 0.85

    # 6. Verify latest DB verdict is NO, and does NOT match the stale verdict ID
    latest_verdict = await VerdictRepository.get_latest_by_company(db_session, company_id)
    assert latest_verdict is not None
    assert latest_verdict.id != stale_verdict_id
    assert latest_verdict.fit == FitDecision.NO
    assert latest_verdict.confidence >= 0.85


@pytest.mark.asyncio
async def test_stale_invalid_verdict_recompute_failure_does_not_surface_invalid_verdict(db_session: AsyncSession) -> None:
    """
    Verify that if a company with ONLY an invalid legacy verdict (UNCERTAIN 0.95) fails recomputation:
    1. It does NOT treat the invalid verdict as a valid prior verdict.
    2. The run telemetry company_results marks status as FAILED with fit=None and confidence=None.
    3. VerdictRepository.get_latest_by_company() returns None (does NOT surface the invalid verdict).
    4. Historical record is preserved in the table for audit.
    """
    from sqlalchemy import insert
    from app.database.models import Verdict

    # 1. Create company in DB
    company = await CompanyRepository.create(
        session=db_session,
        name="Legacy Stale Co",
        website_url="https://legacy-stale.com",
        sheet_row_id="row_legacy_fail",
        status=CompanyStatus.JUDGED,
    )
    company_id = company.id
    await db_session.commit()

    # 2. Insert raw invalid legacy verdict
    stale_verdict_id = uuid.uuid4()
    await db_session.execute(
        insert(Verdict.__table__).values(
            id=stale_verdict_id,
            company_id=company_id,
            fit=FitDecision.UNCERTAIN,
            confidence=0.95,
            reasoning=["Legacy invalid verdict"],
            evaluated_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    # Verify VerdictRepository.get_latest_by_company() ignores the invalid verdict
    assert await VerdictRepository.get_latest_by_company(db_session, company_id) is None
    # Verify historical listing still retains it for audit
    all_history = await VerdictRepository.list_by_company(db_session, company_id)
    assert len(all_history) == 1
    assert all_history[0].id == stale_verdict_id

    # 3. Trigger recomputation with simulated Gemini 429
    llm_service = LLMJudgeService(
        session=db_session,
        llm_client=FakeLLMClient(raise_error=LLMClientError("Gemini API rate limit 429")),
    )
    processor = CompanyProcessor(
        session=db_session,
        http_enrichment_service=MockHttpEnrichmentService(db_session),
        llm_judge_service=llm_service,
        enable_browser=False,
    )
    orchestrator = PipelineOrchestrator(
        session=db_session,
        processor=processor,
    )

    run_result = await orchestrator.run_pipeline(
        PipelineRunRequest(
            company_ids=[company_id],
            skip_ingestion=True,
            sync_to_sheets=False,
            force_reprocess=True,
        )
    )

    # 4. Assert failure is reported cleanly without surfacing the invalid verdict
    assert run_result.companies_failed == 1
    assert len(run_result.company_results) == 1
    failed_result = run_result.company_results[0]
    assert failed_result.status == CompanyStatus.FAILED
    assert failed_result.fit_decision is None
    assert failed_result.confidence is None
    assert "429" in (failed_result.error or "")

    # 5. Assert get_latest_by_company continues to return None
    assert await VerdictRepository.get_latest_by_company(db_session, company_id) is None
