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
