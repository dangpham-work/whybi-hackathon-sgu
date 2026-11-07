"""node_review_windows (hạn kiểm tra bài cũ của nút) for C2-15

Revision ID: 17ea8d98c97a
Revises: 7c3e2a14b5d1
Create Date: 2026-10-20 23:00:45.665356
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '17ea8d98c97a'
down_revision: str | None = '7c3e2a14b5d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'node_review_windows',
        sa.Column('class_id', sa.UUID(), nullable=False),
        sa.Column('node_key', sa.String(length=64), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ['class_id'],
            ['class_sections.id'],
            name=op.f('fk_node_review_windows_class_id_class_sections'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_node_review_windows')),
        sa.UniqueConstraint('class_id', 'node_key', name=op.f('uq_node_review_windows_class_id')),
    )


def downgrade() -> None:
    op.drop_table('node_review_windows')
