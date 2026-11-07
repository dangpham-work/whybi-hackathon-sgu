"""peer_matches studied_by_a / studied_by_b for C2-14

Revision ID: 7c3e2a14b5d1
Revises: 1b1a022b50bd
Create Date: 2026-10-16 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '7c3e2a14b5d1'
down_revision: str | None = '1b1a022b50bd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'peer_matches', sa.Column('studied_by_a', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column(
        'peer_matches', sa.Column('studied_by_b', sa.Boolean(), server_default='false', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('peer_matches', 'studied_by_b')
    op.drop_column('peer_matches', 'studied_by_a')
