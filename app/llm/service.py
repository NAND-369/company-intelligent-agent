"""LLM Judge orchestration service linking PostgreSQL signals, prompt engine, and verdict persistence."""

import logging
from typing import Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import CompanyStatus, FitDecision
from app.database.models import Verdict
from app.database.repositories import (
    CompanyRepository,
    SignalRepository,
    VerdictRepository,
)
from app.llm.client import LLMClient, LLMClientError, get_llm_client
from app.llm.parser import LLMOutputParser
from app.llm.prompt_builder import PromptBuilder
from app.llm.rubric import RubricConfig, load_rubric
from app.llm.schemas import StructuredLLMVerdict

logger = logging.getLogger(__name__)


class LLMJudgeService:
    """Service executing evidence-based structured LLM evaluation and PostgreSQL persistence."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: Optional[LLMClient] = None,
        rubric: Optional[RubricConfig] = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client or get_llm_client()
        self.rubric = rubric or load_rubric()

    async def evaluate_company(
        self,
        company_id: uuid.UUID,
    ) -> Optional[Verdict]:
        """
        Evaluate a target company against the configurable rubric using persisted evidence signals.
        Persists the resulting Verdict in PostgreSQL and updates Company status to EVALUATED.
        """
        company = await CompanyRepository.get_by_id(self.session, company_id)
        if not company:
            logger.error("Company with ID '%s' not found for evaluation.", company_id)
            return None

        # 1. Retrieve all factual signals persisted for this company
        signals = await SignalRepository.list_by_company(self.session, company_id)
        logger.info(
            "Evaluating company '%s' (id=%s) with %d persisted evidence signals.",
            company.name,
            company.id,
            len(signals),
        )

        # 2. Build structured system and user prompts
        system_prompt = PromptBuilder.build_system_prompt()
        user_prompt = PromptBuilder.build_user_prompt(
            company=company,
            signals=signals,
            rubric=self.rubric,
        )

        # 3. Execute LLM inference
        raw_response = await self.llm_client.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 4. Parse, validate, and execute 1-shot JSON repair if necessary
        structured_verdict: StructuredLLMVerdict = await LLMOutputParser.parse_and_validate(
            raw_text=raw_response,
            llm_client=self.llm_client,
            allow_repair=True,
        )

        # 5. Persist valid Verdict in PostgreSQL System of Record
        persisted_verdict = await VerdictRepository.create(
            session=self.session,
            company_id=company.id,
            fit=structured_verdict.fit,
            confidence=structured_verdict.confidence,
            reasoning=structured_verdict.reasoning,
            confidence_rationale=structured_verdict.confidence_rationale,
            follow_up_question=structured_verdict.follow_up_question,
            key_signals_used=structured_verdict.key_signals_used,
            rubric_version=self.rubric.version,
        )

        # 6. Advance Company status to JUDGED
        await CompanyRepository.update_status(
            session=self.session,
            company_id=company.id,
            status=CompanyStatus.JUDGED,
        )

        await self.session.commit()

        logger.info(
            "Verdict successfully recorded for company '%s': Verdict id=%s (fit=%s, confidence=%.2f)",
            company.name,
            persisted_verdict.id,
            persisted_verdict.fit,
            persisted_verdict.confidence,
        )

        return persisted_verdict
