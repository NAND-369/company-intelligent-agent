"""Output validation and 1-shot JSON repair parser for LLM judge responses."""

import json
import logging
import re
from typing import Optional
from pydantic import ValidationError

from app.database.enums import FitDecision
from app.llm.client import LLMClient
from app.llm.prompt_builder import PromptBuilder
from app.llm.schemas import StructuredLLMVerdict

logger = logging.getLogger(__name__)


class LLMOutputParser:
    """Parses, validates, and safely repairs raw LLM JSON outputs into StructuredLLMVerdict."""

    @staticmethod
    def extract_json_block(text: str) -> str:
        """Extract JSON substring from potential markdown fences or surrounding noise."""
        if not text:
            return ""

        text = text.strip()

        # Check for ```json ... ``` markdown block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Find first '{' and last '}'
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx : end_idx + 1].strip()

        return text

    @classmethod
    async def parse_and_validate(
        cls,
        raw_text: str,
        llm_client: Optional[LLMClient] = None,
        allow_repair: bool = True,
    ) -> StructuredLLMVerdict:
        """
        Parse raw model output into a validated StructuredLLMVerdict.
        Executes a 1-shot repair attempt if validation fails.
        """
        cleaned_json = cls.extract_json_block(raw_text)

        try:
            parsed_dict = json.loads(cleaned_json)
            return StructuredLLMVerdict.model_validate(parsed_dict)
        except (json.JSONDecodeError, ValidationError) as initial_err:
            logger.warning("Initial LLM response failed validation: %s", initial_err)

            if allow_repair and llm_client is not None:
                logger.info("Attempting 1-shot JSON format repair with LLM...")
                try:
                    repair_prompt = PromptBuilder.build_repair_prompt(
                        raw_output=raw_text,
                        error_details=str(initial_err),
                    )
                    repaired_text = await llm_client.generate_text(
                        system_prompt="You are a strict JSON schema repair specialist.",
                        user_prompt=repair_prompt,
                    )
                    repaired_json = cls.extract_json_block(repaired_text)
                    repaired_dict = json.loads(repaired_json)
                    verdict = StructuredLLMVerdict.model_validate(repaired_dict)
                    logger.info("1-shot JSON repair successful.")
                    return verdict
                except Exception as repair_err:
                    logger.error("1-shot JSON repair failed: %s", repair_err)

            # Safe fallback verdict when validation/repair fails
            logger.warning("Returning safe UNCERTAIN fallback verdict.")
            return StructuredLLMVerdict(
                fit=FitDecision.UNCERTAIN,
                confidence=0.0,
                confidence_rationale="Evaluation could not be structured due to output validation failure.",
                reasoning=[
                    f"LLM response failed schema validation: {str(initial_err)[:200]}",
                    "Raw evidence remains safely persisted in PostgreSQL for manual audit.",
                ],
                follow_up_question="Manual review required: please inspect company signals.",
                key_signals_used=[],
            )
