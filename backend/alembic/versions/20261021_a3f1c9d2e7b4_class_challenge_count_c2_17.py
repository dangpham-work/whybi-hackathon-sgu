"""class_sections.challenge_count (số câu phản biện của lớp) for C2-17

Revision ID: a3f1c9d2e7b4
Revises: 17ea8d98c97a
Create Date: 2026-10-21 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a3f1c9d2e7b4'
down_revision: str | None = '17ea8d98c97a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'class_sections', sa.Column('challenge_count', sa.SmallInteger(), server_default='3', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('class_sections', 'challenge_count')
