"""Pydantic schemas for the HTTP enrichment subsystem."""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field

from app.database.enums import SignalStatus, SignalType


class DiscoveredLink(BaseModel):
    """A discovered navigation link on a company website."""

    text: str = Field(description="Anchor text or description")
    url: str = Field(description="Normalized absolute URL")
    category: str = Field(description="Category tag, e.g. 'careers', 'about', 'products', 'general'")


class ExtractedPageFacts(BaseModel):
    """Structured, token-efficient facts extracted from a single web page."""

    url: str
    page_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    headings: list[str] = Field(default_factory=list, description="Top H1-H3 headings")
    main_text_snippet: str = Field(default="", description="Bounded primary text content")
    discovered_links: list[DiscoveredLink] = Field(default_factory=list)
    careers_url: Optional[str] = Field(default=None, description="Discovered careers page URL if any")
    raw_size_bytes: int = Field(default=0)


class NormalizedSignalResult(BaseModel):
    """Normalized evidence signal ready for persistence and LLM reasoning."""

    signal_type: SignalType = Field(default=SignalType.HTTP_WEBSITE)
    status: SignalStatus = Field(default=SignalStatus.SUCCESS)
    source_url: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = Field(default=0)
    raw_data: Optional[dict[str, Any]] = Field(default=None)
    extracted_facts: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class HttpEnrichmentResult(BaseModel):
    """Outcome of an HTTP enrichment execution for a company."""

    company_id: uuid.UUID
    signals_collected: list[NormalizedSignalResult] = Field(default_factory=list)
    success: bool = Field(default=True)
    error: Optional[str] = None
    total_duration_ms: int = Field(default=0)
