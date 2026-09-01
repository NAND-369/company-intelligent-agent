"""Configurable evaluation rubric loader and schema definition."""

import logging
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field
import yaml

logger = logging.getLogger(__name__)


class TargetCriteria(BaseModel):
    """Target company profile criteria."""

    industry_focus: str = Field(default="")
    target_offerings: str = Field(default="")
    team_size_indicators: str = Field(default="")


class ConfidenceGuidelines(BaseModel):
    """Thresholds for calibrating confidence score."""

    high_confidence_threshold: float = Field(default=0.85)
    moderate_confidence_threshold: float = Field(default=0.60)
    insufficient_evidence_threshold: float = Field(default=0.30)


class RubricConfig(BaseModel):
    """Complete configurable rubric model."""

    version: str = Field(default="1.0.0")
    rubric_name: str = Field(default="Default Evaluation Rubric")
    description: str = Field(default="")
    target_criteria: TargetCriteria = Field(default_factory=TargetCriteria)
    positive_signals: list[str] = Field(default_factory=list)
    disqualifying_signals: list[str] = Field(default_factory=list)
    confidence_guidelines: ConfidenceGuidelines = Field(default_factory=ConfidenceGuidelines)

    def to_yaml_string(self) -> str:
        """Convert rubric into a clean YAML string for inclusion in LLM prompt."""
        data = self.model_dump()
        return yaml.dump(data, sort_keys=False)


def load_rubric(rubric_path: str = "config/rubric.yaml") -> RubricConfig:
    """Load rubric from YAML file or return default fallback configuration."""
    path = Path(rubric_path)
    if not path.exists():
        logger.warning("Rubric file '%s' not found. Using default rubric configuration.", rubric_path)
        return RubricConfig()

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        return RubricConfig.model_validate(raw_data)
    except Exception as exc:
        logger.error("Failed to parse rubric file '%s': %s. Falling back to default.", rubric_path, exc)
        return RubricConfig()
