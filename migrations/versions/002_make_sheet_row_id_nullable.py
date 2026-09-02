"""002_make_sheet_row_id_nullable

Revision ID: 002_make_sheet_row_id_nullable
Revises: 001_initial_schema
Create Date: 2026-09-02 06:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_make_sheet_row_id_nullable"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make companies.sheet_row_id nullable for dashboard-ingested companies."""
    op.alter_column(
        "companies",
        "sheet_row_id",
        existing_type=sa.String(length=128),
        nullable=True,
    )


def downgrade() -> None:
    """Revert companies.sheet_row_id to NOT NULL."""
    op.alter_column(
        "companies",
        "sheet_row_id",
        existing_type=sa.String(length=128),
        nullable=False,
    )
