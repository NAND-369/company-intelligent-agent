"""Pydantic schemas and serialization models for the REST API."""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.database.enums import CompanyStatus, FitDecision, PipelineRunStatus, TriggerType


class ErrorDetail(BaseModel):
    """Standardized API error envelope payload."""

    code: str
    message: str
    details: Optional[Any] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorResponse(BaseModel):
    """Standardized API error response body."""

    error: ErrorDetail


class DependencyStatus(BaseModel):
    """Operational status of an individual external or internal dependency."""

    status: str
    latency_ms: Optional[int] = None
    engine: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """System health check probe response payload."""

    status: str
    app_name: str
    version: str
    environment: str
    dependencies: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TriggerRunRequest(BaseModel):
    """Payload for requesting an on-demand background pipeline execution."""

    model_config = ConfigDict(extra="ignore")

    batch_size: int = Field(default=20, ge=1, le=500, description="Max pending companies to process")
    limit: Optional[int] = Field(default=None, ge=1, le=500, description="Alias for batch_size")
    force_reprocess: bool = Field(default=False, description="Re-evaluate companies even if previously synced")
    sync_to_sheets: bool = Field(default=True, description="Synchronize verdicts back to Google Sheets")
    skip_ingestion: bool = Field(default=False, description="Skip fetching new rows from Google Sheets")
    dry_run: bool = Field(default=False, description="Preview actions without mutating records")

    @property
    def effective_batch_size(self) -> int:
        """Return resolved batch size considering either batch_size or limit parameter."""
        if self.limit is not None:
            return self.limit
        return self.batch_size


class TriggerRunResponse(BaseModel):
    """HTTP 202 Accepted response for enqueued pipeline runs."""

    run_id: uuid.UUID
    status: str = "RUNNING"
    message: str
    batch_size: int
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    links: dict[str, str]


class PipelineRunMetrics(BaseModel):
    """Structured metrics breakdown for a pipeline run."""

    total_companies_discovered: int
    processed_count: int
    success_count: int
    failed_extraction_count: int
    failed_evaluation_count: int
    synced_to_sheet_count: int


class PipelineRunSummary(BaseModel):
    """Verdict categorization counts for a pipeline run."""

    fit_yes: int
    fit_no: int
    fit_uncertain: int


class PipelineRunDetailResponse(BaseModel):
    """Detailed telemetry and metrics for a specific pipeline execution."""

    run_id: uuid.UUID
    status: PipelineRunStatus
    trigger_source: TriggerType
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metrics: PipelineRunMetrics
    summary: PipelineRunSummary
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CompanyVerdictSummary(BaseModel):
    """Summary of the latest evaluation verdict attached to a company."""

    id: Optional[uuid.UUID] = None
    fit: FitDecision
    confidence: float
    reasoning: list[str]
    follow_up_question: Optional[str] = None
    rubric_version: Optional[str] = None
    evaluated_at: datetime


class CompanyListItem(BaseModel):
    """Paginated list item representing a company and its current evaluation state."""

    id: uuid.UUID
    name: str
    website_url: str
    domain: Optional[str] = None
    sheet_row_id: Optional[str] = None
    status: CompanyStatus
    created_at: datetime
    latest_verdict: Optional[CompanyVerdictSummary] = None


class CompanyListResponse(BaseModel):
    """Paginated company query response envelope."""

    total: int
    limit: int
    offset: int
    items: list[CompanyListItem]


class SignalDetail(BaseModel):
    """Detailed facts extracted by an enrichment provider."""

    signal_type: str
    status: str
    source_url: Optional[str] = None
    extracted_facts: dict[str, Any]
    error_message: Optional[str] = None
    collected_at: datetime


class SyncLogDetail(BaseModel):
    """Google Sheets synchronization attempt audit entry."""

    id: uuid.UUID
    sync_direction: str
    status: str
    error_details: Optional[str] = None
    synced_at: datetime


class CompanyDetailResponse(BaseModel):
    """Complete detail view of a single company with attached signals, verdict, and sync history."""

    id: uuid.UUID
    name: str
    website_url: str
    domain: Optional[str] = None
    sheet_row_id: Optional[str] = None
    status: CompanyStatus
    created_at: datetime
    updated_at: datetime
    signals: list[SignalDetail] = Field(default_factory=list)
    latest_verdict: Optional[CompanyVerdictSummary] = None
    sync_logs: list[SyncLogDetail] = Field(default_factory=list)


class CompanyRetryRequest(BaseModel):
    """Payload for triggering single-company re-evaluation."""

    force_re_enrichment: bool = Field(default=True, description="Force re-crawling website/career pages")


class CompanyRetryResponse(BaseModel):
    """HTTP 202 Accepted response for single-company re-evaluation."""

    company_id: uuid.UUID
    status: str = "PROCESSING"
    message: str
    scheduled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
