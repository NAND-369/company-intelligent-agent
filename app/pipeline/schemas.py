"""Pydantic models and result schemas for the pipeline orchestration subsystem."""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field

from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    TriggerType,
)


class PipelineRunRequest(BaseModel):
    """Payload for triggering an on-demand pipeline execution."""

    run_id: Optional[uuid.UUID] = Field(default=None, description="Optional pre-allocated PipelineRun UUID to reuse")
    company_ids: Optional[list[uuid.UUID]] = Field(default=None, description="Explicit company UUIDs to process in this run (if provided, only these companies are evaluated)")
    limit: Optional[int] = Field(default=None, ge=1, le=500, description="Max companies to process in this run")
    force_reprocess: bool = Field(default=False, description="Re-evaluate companies even if previously synced or judged")
    dry_run: bool = Field(default=False, description="Preview actions without mutating database state")
    skip_ingestion: bool = Field(default=False, description="Skip Google Sheets fetch and process existing DB companies")
    sync_to_sheets: bool = Field(default=False, description="Synchronize evaluated verdicts back to Google Sheets rows")
    trigger_type: TriggerType = Field(default=TriggerType.ON_DEMAND_API, description="Pipeline trigger origin")


class PipelineCompanyResult(BaseModel):
    """Execution telemetry for a single company within a pipeline run."""

    company_id: uuid.UUID
    company_name: str
    website_url: str
    status: CompanyStatus
    fit_decision: Optional[FitDecision] = None
    confidence: Optional[float] = None
    reasoning: list[str] = Field(default_factory=list)
    follow_up_question: Optional[str] = None
    signals_count: int = 0
    is_synced: bool = False
    error: Optional[str] = None
    duration_ms: int = 0


class PipelineRunResult(BaseModel):
    """Comprehensive execution telemetry and outcome metrics for a pipeline run."""

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    status: PipelineRunStatus = Field(default=PipelineRunStatus.COMPLETED)
    trigger_type: TriggerType = Field(default=TriggerType.ON_DEMAND_API)
    dry_run: bool = Field(default=False)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_seconds: float = Field(default=0.0)

    # Counters
    companies_discovered: int = 0
    companies_processed: int = 0
    companies_succeeded: int = 0
    companies_failed: int = 0
    synced_count: int = 0
    fit_yes_count: int = 0
    fit_no_count: int = 0
    fit_uncertain_count: int = 0

    errors: list[str] = Field(default_factory=list)
    company_results: list[PipelineCompanyResult] = Field(default_factory=list)
