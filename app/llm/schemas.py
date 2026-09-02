"""Pydantic schemas and structured output contracts for the LLM judge."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from app.database.enums import FitDecision


class StructuredLLMVerdict(BaseModel):
    """Strict structured output contract for evidence-grounded company fit judgments with explicit precedence."""

    disqualified_by_evidence: bool = Field(
        default=False,
        description="True if verified evidence establishes a disqualifying business model/category (e.g. B2C e-commerce, consumer retail, fashion/clothing retail, groceries, consumer marketplace, physical goods, agency, parked domain)."
    )
    disqualification_reason: Optional[str] = Field(
        default=None,
        description="Specific citation from evidence explaining why company is disqualified, or null."
    )
    qualified_by_evidence: bool = Field(
        default=False,
        description="True if verified evidence establishes target B2B software, enterprise tech, developer platforms/APIs, AI/ML infrastructure, or enterprise SaaS."
    )
    qualification_reason: Optional[str] = Field(
        default=None,
        description="Specific citation from evidence explaining why company meets target criteria, or null."
    )
    reasoning: list[str] = Field(
        ...,
        min_length=1,
        description="List of distinct, evidence-grounded deductive statements citing supplied facts"
    )
    fit: FitDecision = Field(
        ...,
        description="Categorical decision derived strictly by precedence: 1. If disqualified_by_evidence -> NO; 2. Else if qualified_by_evidence -> YES; 3. Else -> UNCERTAIN"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated confidence score from 0.0 (no confidence) to 1.0 (absolute certainty)"
    )
    confidence_rationale: Optional[str] = Field(
        default=None,
        description="Concise rationale explaining the confidence level assignment"
    )
    follow_up_question: Optional[str] = Field(
        default=None,
        description="Targeted discovery question to clarify ambiguity or missing evidence"
    )
    key_signals_used: list[str] = Field(
        default_factory=list,
        description="Types of signals referenced in the reasoning (e.g. HTTP_WEBSITE, BROWSER_CAREERS)"
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("Confidence score must be strictly between 0.0 and 1.0 inclusive.")
        return round(v, 4)

    @field_validator("reasoning")
    @classmethod
    def validate_reasoning_non_empty(cls, v: list[str]) -> list[str]:
        cleaned = [r.strip() for r in v if r and r.strip()]
        if not cleaned:
            raise ValueError("Reasoning must contain at least one non-empty statement.")
        return cleaned

    @classmethod
    def from_validated_data(cls, data: dict) -> "StructuredLLMVerdict":
        """Helper to create and validate verdict."""
        return cls.model_validate(data)

    @model_validator(mode="after")
    def validate_fit_consistency_and_precedence(self) -> "StructuredLLMVerdict":
        """
        Enforce decision precedence & semantic consistency:
        1. If disqualified_by_evidence is True -> fit MUST be NO.
        2. Else if qualified_by_evidence is True -> fit MUST be YES.
        3. UNCERTAIN verdict must have confidence < 0.50.
        4. YES or NO verdict must have confidence >= 0.50.
        """
        if self.disqualified_by_evidence and self.fit != FitDecision.NO:
            raise ValueError(
                f"Inconsistent model response: disqualified_by_evidence is True, so fit MUST be NO (received fit={self.fit.value})."
            )

        if self.qualified_by_evidence and not self.disqualified_by_evidence and self.fit != FitDecision.YES:
            raise ValueError(
                f"Inconsistent model response: qualified_by_evidence is True, so fit MUST be YES (received fit={self.fit.value})."
            )

        if self.fit == FitDecision.UNCERTAIN and self.confidence >= 0.50:
            raise ValueError(
                f"Inconsistent model response: UNCERTAIN verdict must have confidence < 0.50 (received {self.confidence})."
            )

        if self.fit in (FitDecision.YES, FitDecision.NO) and self.confidence < 0.50:
            raise ValueError(
                f"Inconsistent model response: Conclusive {self.fit.value} verdict must have confidence >= 0.50 (received {self.confidence})."
            )

        return self
