"""Pydantic schemas for Google Sheets output synchronization."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field


class SyncOutcome(str, Enum):
    """Synchronization outcome categories."""

    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class SyncCompanyResult(BaseModel):
    """Synchronization outcome telemetry for an individual company."""

    company_id: uuid.UUID
    company_name: str
    sheet_row_id: str
    row_index: int
    status: SyncOutcome
    fingerprint: Optional[str] = None
    updates: dict[str, Any] = Field(default_factory=dict, description="Mapped column key-value updates written")
    error_details: Optional[str] = None
    synced_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncBatchResult(BaseModel):
    """Aggregate telemetry from a Google Sheets synchronization run."""

    spreadsheet_id: str = ""
    worksheet_name: str = ""
    total_candidates: int = 0
    synced_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = Field(default_factory=list)
    company_results: list[SyncCompanyResult] = Field(default_factory=list)
