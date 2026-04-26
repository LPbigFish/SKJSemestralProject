"""add_queued_messages_table

Revision ID: acf5ab4b2635
Revises: a974f20ec073
Create Date: 2026-04-23 20:31:46.981665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'acf5ab4b2635'
down_revision: Union[str, Sequence[str], None] = 'a974f20ec073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'queued_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('topic', sa.String(), nullable=False),
        sa.Column('payload', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_delivered', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_queued_messages_topic'), 'queued_messages', ['topic'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_queued_messages_topic'), table_name='queued_messages')
    op.drop_table('queued_messages')
