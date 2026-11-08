"""concept_nodes.source_page_start/end và aliases (trang nguồn của nút, key cũ khi gộp nút) for C1-20

Revision ID: c120e5b7a9d3
Revises: 412b81e85505
Create Date: 2026-11-08 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = 'c120e5b7a9d3'
down_revision: str | None = '412b81e85505'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('concept_nodes', sa.Column('source_page_start', sa.SmallInteger(), nullable=True))
    op.add_column('concept_nodes', sa.Column('source_page_end', sa.SmallInteger(), nullable=True))
    op.add_column(
        'concept_nodes',
        sa.Column('aliases', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('concept_nodes', 'aliases')
    op.drop_column('concept_nodes', 'source_page_end')
    op.drop_column('concept_nodes', 'source_page_start')
