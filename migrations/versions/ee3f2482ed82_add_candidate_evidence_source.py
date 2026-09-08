"""add candidate evidence source

Revision ID: ee3f2482ed82
Revises: d3914ad4cef7
Create Date: 2026-09-06 00:18:03.629447

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ee3f2482ed82'
down_revision: str | Sequence[str] | None = 'd3914ad4cef7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "memory_candidates",
        sa.Column(
            "evidence_source",
            sa.String(length=50),
            server_default="observation",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("memory_candidates", "evidence_source")
