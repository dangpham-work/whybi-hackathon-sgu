"""usage_records.provider/model for C2-24

Revision ID: e7a1f3c9b2d4
Revises: c120e5b7a9d3
Create Date: 2026-11-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e7a1f3c9b2d4"
down_revision: str | None = "c120e5b7a9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("provider", sa.String(length=40), nullable=True))
    op.add_column("usage_records", sa.Column("model", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "model")
    op.drop_column("usage_records", "provider")
