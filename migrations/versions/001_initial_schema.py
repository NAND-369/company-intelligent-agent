"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-01 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. companies table
    op.create_table(
        "companies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=1024), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("sheet_row_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_domain", "companies", ["domain"], unique=False)
    op.create_index("ix_companies_sheet_row_id", "companies", ["sheet_row_id"], unique=True)
    op.create_index("ix_companies_status", "companies", ["status"], unique=False)

    # 2. signals table
    op.create_table(
        "signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="SUCCESS", nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_company_id", "signals", ["company_id"], unique=False)
    op.create_index("ix_signals_signal_type", "signals", ["signal_type"], unique=False)
    op.create_index("ix_signals_collected_at", "signals", ["collected_at"], unique=False)

    # 3. verdicts table
    op.create_table(
        "verdicts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("fit", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_rationale", sa.Text(), nullable=True),
        sa.Column("reasoning", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("follow_up_question", sa.Text(), nullable=True),
        sa.Column("key_signals_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rubric_version", sa.String(length=64), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verdicts_company_id", "verdicts", ["company_id"], unique=False)
    op.create_index("ix_verdicts_fit", "verdicts", ["fit"], unique=False)
    op.create_index("ix_verdicts_evaluated_at", "verdicts", ["evaluated_at"], unique=False)

    # 4. sync_logs table
    op.create_table(
        "sync_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("sync_direction", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_logs_company_id", "sync_logs", ["company_id"], unique=False)
    op.create_index("ix_sync_logs_status", "sync_logs", ["status"], unique=False)
    op.create_index("ix_sync_logs_synced_at", "sync_logs", ["synced_at"], unique=False)

    # 5. pipeline_runs table
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("total_companies", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_extraction_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_evaluation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("synced_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fit_yes_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fit_no_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fit_uncertain_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"], unique=False)
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("pipeline_runs")
    op.drop_table("sync_logs")
    op.drop_table("verdicts")
    op.drop_table("signals")
    op.drop_table("companies")
