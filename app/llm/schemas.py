"""Pydantic schemas and structured output contracts for the LLM judge."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from app.database.enums import FitDecision


class StructuredLLMVerdict(BaseModel):
    """Strict structured output contract for evidence-grounded company fit judgments."""

    fit: FitDecision = Field(
        ...,
        description="Categorical decision: YES (meets rubric criteria), NO (disqualified/does not meet), UNCERTAIN (insufficient/ambiguous data)"
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
    reasoning: list[str] = Field(
        ...,
        min_length=1,
        description="List of distinct, evidence-grounded deductive statements citing supplied facts"
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
    def validate_fit_confidence_consistency(self) -> "StructuredLLMVerdict":
        """
        Enforce semantic consistency: UNCERTAIN decisions must have confidence < 0.50.
        Internally inconsistent combinations (e.g. UNCERTAIN with 0.95 confidence)
        are rejected as invalid model responses rather than silently modified.
        """
        if self.fit == FitDecision.UNCERTAIN and self.confidence >= 0.50:
            raise ValueError(
                f"Inconsistent model response: UNCERTAIN verdict must have confidence < 0.50 (received {self.confidence})."
            )
        return self
