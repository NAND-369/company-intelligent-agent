"""Prompt assembly engine for evidence-grounded LLM company evaluation."""

import json
from typing import Any, Sequence
from app.database.models import Company, Signal
from app.llm.rubric import RubricConfig


SYSTEM_PROMPT = """You are the Lead Company Evaluation Judge in an automated intelligence pipeline.
Your job is to evaluate whether a target company is a "FIT" for the configured business profile based EXCLUSIVELY on the supplied evidence signals and the provided evaluation rubric.

ABSOLUTE CONSTRAINTS:
1. Reason ONLY from the extracted evidence signals provided in the prompt.
2. Do NOT invent facts, technologies, job roles, company activities, or metrics not present in the evidence.
3. Do NOT attempt external web research or make assumptions based on outside knowledge.
4. Distinguish clearly between direct factual observations and logical inferences.
5. If the evidence is insufficient, contradictory, or absent, you MUST set "fit" to "UNCERTAIN", calibrate confidence low (<0.40), and provide a targeted "follow_up_question".
6. Output MUST be valid JSON adhering strictly to the required schema. No conversational preamble or trailing commentary.

REQUIRED JSON OUTPUT FORMAT:
{
  "fit": "YES" | "NO" | "UNCERTAIN",
  "confidence": 0.0 - 1.0,
  "confidence_rationale": "Brief rationale for confidence score",
  "reasoning": [
    "Evidence-grounded deductive statement citing specific facts"
  ],
  "follow_up_question": "Targeted discovery question for missing info or null",
  "key_signals_used": ["HTTP_WEBSITE", "BROWSER_CAREERS"]
}
"""


class PromptBuilder:
    """Constructs token-bounded, structured evaluation prompts."""

    MAX_SIGNAL_CHARS = 4800  # ~1,200 tokens cap per signal

    @classmethod
    def build_system_prompt(cls) -> str:
        """Return the standard system prompt."""
        return SYSTEM_PROMPT.strip()

    @classmethod
    def build_user_prompt(
        cls,
        company: Company,
        signals: Sequence[Signal],
        rubric: RubricConfig,
    ) -> str:
        """Construct user prompt incorporating rubric, company metadata, and bounded signals."""
        rubric_yaml = rubric.to_yaml_string()

        # Format and bound evidence signals
        formatted_signals: list[str] = []
        if not signals:
            formatted_signals.append("NO EVIDENCE SIGNALS AVAILABLE: No website or browser signals have been collected.")
        else:
            for idx, sig in enumerate(signals, 1):
                facts_json = json.dumps(sig.extracted_facts, indent=2, default=str)
                if len(facts_json) > cls.MAX_SIGNAL_CHARS:
                    facts_json = facts_json[: cls.MAX_SIGNAL_CHARS] + "\n... [TRUNCATED DUE TO SIZE LIMIT]"

                formatted_signals.append(
                    f"Signal #{idx} [Type: {sig.signal_type}, Status: {sig.status}, Source: {sig.source_url}]:\n{facts_json}"
                )

        signals_block = "\n\n".join(formatted_signals)

        user_prompt = f"""Evaluate the following company against the configured evaluation rubric:

### 1. CONFIGURABLE EVALUATION RUBRIC (v{rubric.version})
```yaml
{rubric_yaml}
```

### 2. TARGET COMPANY IDENTIFIERS
- Company Name: {company.name}
- Registered Website: {company.website_url}
- Ingestion Domain: {company.domain or 'N/A'}

### 3. PERSISTED FACTUAL EVIDENCE SIGNALS ({len(signals)} collected)
{signals_block}

### 4. INSTRUCTIONS
Synthesize the supplied evidence against the rubric criteria and output the structured evaluation verdict in valid JSON.
Remember: If facts are missing or uncertain, return fit: "UNCERTAIN" with a constructive follow_up_question.
"""
        return user_prompt.strip()

    @classmethod
    def build_repair_prompt(cls, raw_output: str, error_details: str) -> str:
        """Construct one-shot JSON repair prompt."""
        return f"""The previous response failed schema validation.

VALIDATION ERROR:
{error_details}

ORIGINAL RAW RESPONSE:
{raw_output}

INSTRUCTION:
Repair the output and return ONLY the corrected, valid JSON object conforming strictly to the required schema:
{{
  "fit": "YES" | "NO" | "UNCERTAIN",
  "confidence": float (0.0 to 1.0),
  "confidence_rationale": "string",
  "reasoning": ["string statement"],
  "follow_up_question": "string or null",
  "key_signals_used": ["string"]
}}
"""
