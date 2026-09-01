"""SQLAlchemy 2.0 ORM domain models for the PostgreSQL System of Record."""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.database.enums import (
    CompanyStatus,
    FitDecision,
    PipelineRunStatus,
    SignalStatus,
    SignalType,
    SyncDirection,
    SyncStatus,
    TriggerType,
)
from app.database.session import Base


# Universal JSON type that uses JSONB on PostgreSQL and JSON elsewhere (e.g. SQLite tests)
class JSONType(TypeDecorator):
    """Platform-independent JSON/JSONB type."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Company(Base):
    """Target company discovered and ingested from the Google Sheet."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Unique constraint on Google Sheet row identity guarantees idempotent ingestion
    sheet_row_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[CompanyStatus] = mapped_column(
        String(32),
        nullable=False,
        default=CompanyStatus.PENDING,
        index=True,
    )

    # Concurrency lease locking timestamp
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    signals: Mapped[list["Signal"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="Signal.collected_at",
    )
    verdicts: Mapped[list["Verdict"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="Verdict.evaluated_at.desc()",
    )
    sync_logs: Mapped[list["SyncLog"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="SyncLog.synced_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}', status='{self.status}')>"


class Signal(Base):
    """An independently collected piece of evidence for a company."""

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_type: Mapped[SignalType] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped[SignalStatus] = mapped_column(
        String(32),
        nullable=False,
        default=SignalStatus.SUCCESS,
    )
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Full raw dump and distilled facts
    raw_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONType,
        nullable=True,
    )
    extracted_facts: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=dict,
    )

    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Relationship
    company: Mapped["Company"] = relationship(back_populates="signals")

    def __repr__(self) -> str:
        return f"<Signal(id={self.id}, type='{self.signal_type}', status='{self.status}')>"


class Verdict(Base):
    """Structured LLM evaluation judgment for a target company."""

    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fit: Mapped[FitDecision] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON Array of deductive evidence-grounded statements
    reasoning: Mapped[list[str]] = mapped_column(
        JSONType,
        nullable=False,
    )

    follow_up_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_signals_used: Mapped[Optional[list[str]]] = mapped_column(JSONType, nullable=True)
    rubric_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )

    # Relationship
    company: Mapped["Company"] = relationship(back_populates="verdicts")

    def __repr__(self) -> str:
        return f"<Verdict(id={self.id}, fit='{self.fit}', confidence={self.confidence})>"


class SyncLog(Base):
    """Audit record of synchronization attempts with Google Sheets."""

    __tablename__ = "sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sync_direction: Mapped[SyncDirection] = mapped_column(
        String(32),
        nullable=False,
    )
    status: Mapped[SyncStatus] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Relationship
    company: Mapped["Company"] = relationship(back_populates="sync_logs")

    def __repr__(self) -> str:
        return f"<SyncLog(id={self.id}, status='{self.status}', direction='{self.sync_direction}')>"


class PipelineRun(Base):
    """Telemetry and execution metrics for a pipeline batch run."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        String(32),
        nullable=False,
        default=PipelineRunStatus.PENDING,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Progress & evaluation counters
    total_companies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_extraction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_evaluation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fit_yes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fit_no_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fit_uncertain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONType,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<PipelineRun(id={self.id}, status='{self.status}', trigger='{self.trigger_type}')>"
