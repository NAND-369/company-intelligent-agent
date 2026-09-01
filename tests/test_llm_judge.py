"""Comprehensive tests for the evidence-based LLM Judge subsystem."""

import json
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, FitDecision, SignalStatus, SignalType
from app.database.models import Company, Signal
from app.database.repositories import (
    CompanyRepository,
    SignalRepository,
    VerdictRepository,
)
from app.llm.client import FakeLLMClient, LLMClientError, LLMRateLimitError
from app.llm.parser import LLMOutputParser
from app.llm.prompt_builder import PromptBuilder
from app.llm.rubric import RubricConfig, load_rubric
from app.llm.schemas import StructuredLLMVerdict
from app.llm.service import LLMJudgeService


# ==============================================================================
# 1. Schema & Validation Unit Tests
# ==============================================================================

def test_structured_verdict_valid_contract() -> None:
    """Test valid StructuredLLMVerdict creation and field types."""
    verdict = StructuredLLMVerdict(
        fit=FitDecision.YES,
        confidence=0.92,
        confidence_rationale="High concordance on B2B SaaS criteria.",
        reasoning=[
            "HTTP website signal demonstrates enterprise cloud platform.",
            "Browser careers signal confirms active hiring for Python and Kubernetes.",
        ],
        follow_up_question=None,
        key_signals_used=["HTTP_WEBSITE", "BROWSER_CAREERS"],
    )

    assert verdict.fit == FitDecision.YES
    assert verdict.confidence == 0.92
    assert len(verdict.reasoning) == 2


def test_structured_verdict_invalid_confidence_bounds() -> None:
    """Test that confidence values outside [0.0, 1.0] are rejected."""
    with pytest.raises(ValidationError):
        StructuredLLMVerdict(
            fit=FitDecision.YES,
            confidence=1.5,  # Exceeds 1.0
            reasoning=["Valid reasoning"],
        )

    with pytest.raises(ValidationError):
        StructuredLLMVerdict(
            fit=FitDecision.NO,
            confidence=-0.1,  # Negative
            reasoning=["Valid reasoning"],
        )


def test_structured_verdict_empty_reasoning_rejected() -> None:
    """Test that empty reasoning array is rejected by Pydantic validation."""
    with pytest.raises(ValidationError):
        StructuredLLMVerdict(
            fit=FitDecision.UNCERTAIN,
            confidence=0.5,
            reasoning=[],  # Empty
        )


# ==============================================================================
# 2. Prompt Builder & Token Bounding Tests
# ==============================================================================

def test_prompt_builder_bounds_oversized_signals() -> None:
    """Test that gigantic signal payloads are truncated before prompt assembly."""
    company = Company(
        name="Huge Payload Corp",
        website_url="https://huge-payload.com",
    )
    oversized_text = "X" * 10000
    signal = Signal(
        signal_type=SignalType.HTTP_WEBSITE,
        status=SignalStatus.SUCCESS,
        source_url="https://huge-payload.com",
        extracted_facts={"giant_field": oversized_text},
    )
    rubric = RubricConfig()

    user_prompt = PromptBuilder.build_user_prompt(company, [signal], rubric)
    assert "[TRUNCATED DUE TO SIZE LIMIT]" in user_prompt
    assert len(user_prompt) < 15000  # Stays well below total budget


def test_prompt_builder_handles_empty_signals() -> None:
    """Test prompt builder when zero signals exist."""
    company = Company(name="No Signals Inc", website_url="https://no-signals.com")
    rubric = RubricConfig()
    user_prompt = PromptBuilder.build_user_prompt(company, [], rubric)

    assert "NO EVIDENCE SIGNALS AVAILABLE" in user_prompt


# ==============================================================================
# 3. JSON Output Parsing and 1-Shot Repair Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_parser_extracts_from_markdown_fences() -> None:
    """Test that JSON wrapped in markdown code blocks is correctly extracted and parsed."""
    raw_markdown = """
    Here is my evaluation verdict:
    ```json
    {
        "fit": "YES",
        "confidence": 0.85,
        "confidence_rationale": "Enterprise automation product.",
        "reasoning": ["Company sells AI workflow automation to logistics hubs."],
        "follow_up_question": null,
        "key_signals_used": ["HTTP_WEBSITE"]
    }
    ```
    """
    verdict = await LLMOutputParser.parse_and_validate(raw_markdown, allow_repair=False)
    assert verdict.fit == FitDecision.YES
    assert verdict.confidence == 0.85
    assert len(verdict.reasoning) == 1


@pytest.mark.asyncio
async def test_parser_one_shot_repair_success() -> None:
    """Test that malformed JSON triggers 1-shot repair and validates repaired response."""
    broken_json = '{ "fit": "YES", confidence: 0.85, broken_syntax... '
    valid_repaired_json = json.dumps({
        "fit": "YES",
        "confidence": 0.85,
        "confidence_rationale": "Repaired JSON output.",
        "reasoning": ["Repaired valid statement."],
        "follow_up_question": None,
        "key_signals_used": ["HTTP_WEBSITE"],
    })

    fake_client = FakeLLMClient(responses=[valid_repaired_json])
    verdict = await LLMOutputParser.parse_and_validate(
        raw_text=broken_json,
        llm_client=fake_client,
        allow_repair=True,
    )

    assert verdict.fit == FitDecision.YES
    assert verdict.confidence == 0.85
    assert len(fake_client.call_history) == 1  # 1 repair call made


@pytest.mark.asyncio
async def test_parser_repair_failure_fallback_uncertain() -> None:
    """Test that when 1-shot repair also fails, a safe UNCERTAIN verdict is generated."""
    broken_json = 'unparseable garbage'
    still_broken_repair = 'still broken garbage'

    fake_client = FakeLLMClient(responses=[still_broken_repair])
    verdict = await LLMOutputParser.parse_and_validate(
        raw_text=broken_json,
        llm_client=fake_client,
        allow_repair=True,
    )

    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence == 0.0
    assert "failed" in verdict.reasoning[0].lower() and "validation" in verdict.reasoning[0].lower()


# ==============================================================================
# 4. LLMJudgeService End-to-End Evaluation & PostgreSQL Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_judge_strong_yes_verdict(db_session: AsyncSession) -> None:
    """Test evaluation of company with strong B2B technology evidence yielding YES."""
    company = await CompanyRepository.create(
        session=db_session,
        name="OmniFleet Robotics",
        website_url="https://omnifleet.io",
        sheet_row_id="row_llm_yes",
        status=CompanyStatus.ENRICHED,
    )
    await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        source_url="https://omnifleet.io",
        extracted_facts={
            "page_title": "OmniFleet - Autonomous Warehouse Fleet Management",
            "headings_summary": ["Enterprise Fleet Dispatch", "Cloud Logistics Platform"],
            "main_content_snippet": "OmniFleet provides B2B SaaS and robotics automation for global supply chains.",
        },
    )
    await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.BROWSER_CAREERS,
        source_url="https://omnifleet.io/careers",
        extracted_facts={
            "active_jobs_count": 4,
            "job_titles": ["Senior Backend Python Engineer", "Robotics Systems Lead"],
            "tech_stack_detected_in_jobs": ["Python", "FastAPI", "PostgreSQL", "ROS2", "Docker"],
        },
    )
    await db_session.commit()

    yes_response = json.dumps({
        "fit": "YES",
        "confidence": 0.94,
        "confidence_rationale": "Concordant B2B robotics platform with active multi-role engineering hiring.",
        "reasoning": [
            "HTTP website signal confirms enterprise autonomous fleet management platform.",
            "Browser careers signal verifies 4 open technical positions requiring Python, FastAPI, and ROS2.",
        ],
        "follow_up_question": None,
        "key_signals_used": ["HTTP_WEBSITE", "BROWSER_CAREERS"],
    })

    fake_client = FakeLLMClient(responses=[yes_response])
    service = LLMJudgeService(session=db_session, llm_client=fake_client)

    verdict = await service.evaluate_company(company.id)

    assert verdict is not None
    assert verdict.fit == FitDecision.YES
    assert verdict.confidence == 0.94
    assert len(verdict.reasoning) == 2

    # Verify company updated to JUDGED
    updated_company = await CompanyRepository.get_by_id(db_session, company.id)
    assert updated_company.status == CompanyStatus.JUDGED

    # Verify verdict persisted in PostgreSQL
    db_verdict = await VerdictRepository.get_latest_by_company(db_session, company.id)
    assert db_verdict is not None
    assert db_verdict.id == verdict.id
    assert db_verdict.fit == FitDecision.YES


@pytest.mark.asyncio
async def test_llm_judge_strong_no_disqualified_verdict(db_session: AsyncSession) -> None:
    """Test evaluation of company meeting disqualifying criteria (e.g. consumer clothing retail)."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Trendy Threads Shop",
        website_url="https://trendy-threads-retail.com",
        sheet_row_id="row_llm_no",
        status=CompanyStatus.ENRICHED,
    )
    await SignalRepository.create(
        session=db_session,
        company_id=company.id,
        signal_type=SignalType.HTTP_WEBSITE,
        source_url="https://trendy-threads-retail.com",
        extracted_facts={
            "page_title": "Trendy Threads - Women's Fast Fashion Retail",
            "headings_summary": ["Summer Dresses On Sale", "Free Shipping on Orders Over $50"],
            "main_content_snippet": "Direct to consumer online clothing boutique.",
        },
    )
    await db_session.commit()

    service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())
    verdict = await service.evaluate_company(company.id)

    assert verdict is not None
    assert verdict.fit == FitDecision.NO
    assert verdict.confidence >= 0.80
    assert "retail" in verdict.reasoning[0].lower() or "disqualif" in verdict.reasoning[0].lower()


@pytest.mark.asyncio
async def test_llm_judge_insufficient_evidence_verdict(db_session: AsyncSession) -> None:
    """Test evaluation when zero or failed signals exist yielding UNCERTAIN and follow-up question."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Empty Signals LLC",
        website_url="https://dead-domain.io",
        sheet_row_id="row_llm_uncertain",
        status=CompanyStatus.PENDING,
    )
    await db_session.commit()

    service = LLMJudgeService(session=db_session, llm_client=FakeLLMClient())
    verdict = await service.evaluate_company(company.id)

    assert verdict is not None
    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence <= 0.30
    assert verdict.follow_up_question is not None


@pytest.mark.asyncio
async def test_llm_judge_provider_outage_fallback(db_session: AsyncSession) -> None:
    """Test that provider errors (outage / 503 / unhandled) safely record UNCERTAIN verdict without crashing."""
    company = await CompanyRepository.create(
        session=db_session,
        name="Crash Test Co",
        website_url="https://crash-test.com",
        sheet_row_id="row_llm_crash",
    )
    await db_session.commit()

    class OutageClient(FakeLLMClient):
        async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
            raise LLMClientError("Gemini API HTTP 503 Service Unavailable")

    service = LLMJudgeService(session=db_session, llm_client=OutageClient())
    verdict = await service.evaluate_company(company.id)

    assert verdict is not None
    assert verdict.fit == FitDecision.UNCERTAIN
    assert verdict.confidence == 0.0
    assert "HTTP 503" in verdict.reasoning[0]


@pytest.mark.asyncio
async def test_gemini_client_header_auth_and_url_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GeminiLLMClient sends API key via x-goog-api-key header and never in URL query params."""
    import httpx
    from app.llm.client import GeminiLLMClient

    captured_request: dict = {}
    secret_key = "AIzaSySecretTestKey123456"

    async def mock_post(self, url, headers=None, params=None, json=None):
        captured_request["url"] = str(url)
        captured_request["headers"] = headers or {}
        captured_request["params"] = params
        captured_request["json"] = json
        return httpx.Response(
            status_code=200,
            json={"candidates": [{"content": {"parts": [{"text": '{"fit": "YES"}'}]}}]},
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = GeminiLLMClient(api_key=secret_key, model="gemini-3.6-flash")
    await client.generate_text("System", "User")

    assert captured_request["headers"].get("x-goog-api-key") == secret_key
    assert captured_request["params"] is None
    assert secret_key not in captured_request["url"]
    assert "/models/gemini-3.6-flash:generateContent" in captured_request["url"]
    assert captured_request["json"]["generationConfig"] == {"response_mime_type": "application/json"}


@pytest.mark.asyncio
async def test_gemini_client_structured_404_error_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify GeminiLLMClient extracts structured Google error details without leaking secrets."""
    import httpx
    from app.llm.client import GeminiLLMClient, LLMClientError

    secret_key = "AIzaSySecretTestKey123456"

    async def mock_post_404(self, url, headers=None, params=None, json=None):
        return httpx.Response(
            status_code=404,
            json={
                "error": {
                    "code": 404,
                    "message": "models/gemini-3.6-flash is not found for API version v1beta",
                    "status": "NOT_FOUND",
                }
            },
            request=httpx.Request("POST", str(url)),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_404)

    client = GeminiLLMClient(api_key=secret_key, model="gemini-3.6-flash")
    with pytest.raises(LLMClientError) as exc_info:
        await client.generate_text("System", "User")

    err_msg = str(exc_info.value)
    assert "models/gemini-3.6-flash is not found" in err_msg
    assert "HTTP 404" in err_msg
    assert "code: 404" in err_msg
    assert "status: NOT_FOUND" in err_msg
    assert secret_key not in err_msg
