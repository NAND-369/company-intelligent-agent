"""Pydantic schemas for Google Sheets row parsing and ingestion telemetry."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ParsedCompanyRow(BaseModel):
    """Normalized company data extracted from a single Google Sheet row."""

    sheet_row_id: str = Field(description="Stable row identity, e.g. 'row_2'")
    row_index: int = Field(description="1-based row index in spreadsheet")
    name: str = Field(description="Normalized company name")
    website_url: str = Field(description="Normalized target website URL")
    domain: Optional[str] = Field(default=None, description="Extracted clean domain (e.g. acme.com)")
    status_raw: Optional[str] = Field(default=None, description="Raw status value from sheet if present")
    extra_data: dict[str, Any] = Field(default_factory=dict, description="Additional unmapped column values")


class RowValidationError(BaseModel):
    """Validation failure recorded for a malformed spreadsheet row."""

    row_index: int = Field(description="1-based row index that failed validation")
    field: str = Field(description="Field name or column causing the error")
    message: str = Field(description="Detailed explanation of the validation failure")
    raw_values: dict[str, Any] = Field(default_factory=dict, description="Raw row contents")


class IngestionResult(BaseModel):
    """Aggregate statistics and outcomes from a Google Sheets ingestion cycle."""

    spreadsheet_id: str = Field(default="", description="Target Google Spreadsheet ID")
    worksheet_name: str = Field(default="", description="Target worksheet/tab name")
    rows_read: int = Field(default=0, description="Total non-header rows read from sheet")
    companies_created: int = Field(default=0, description="New companies persisted in database")
    companies_updated: int = Field(default=0, description="Existing companies updated in database")
    rows_skipped: int = Field(default=0, description="Empty or invalid rows skipped")
    validation_errors: list[RowValidationError] = Field(
        default_factory=list, description="Validation issues encountered per row"
    )
    errors: list[str] = Field(
        default_factory=list, description="Top-level system or API errors encountered"
    )
    created_company_ids: list[str] = Field(
        default_factory=list, description="UUIDs of newly created companies"
    )
    updated_company_ids: list[str] = Field(
        default_factory=list, description="UUIDs of updated existing companies"
    )
    imported_companies: list[dict[str, Any]] = Field(
        default_factory=list, description="List of imported company detail payloads for UI"
    )
