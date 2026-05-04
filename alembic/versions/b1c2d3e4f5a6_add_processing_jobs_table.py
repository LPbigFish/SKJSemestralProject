"""add_processing_jobs_table

Revision ID: b1c2d3e4f5a6
Revises: acf5ab4b2635
Create Date: 2026-05-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'acf5ab4b2635'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_file_id', sa.String(), nullable=False),
        sa.Column('bucket_id', sa.Integer(), nullable=False),
        sa.Column('operation', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='processing'),
        sa.Column('result_file_id', sa.String(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['original_file_id'], ['files.id']),
        sa.ForeignKeyConstraint(['result_file_id'], ['files.id']),
        sa.ForeignKeyConstraint(['bucket_id'], ['buckets.id']),
    )
    op.create_index(
        op.f('ix_processing_jobs_original_file_id'),
        'processing_jobs',
        ['original_file_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_processing_jobs_original_file_id'),
        table_name='processing_jobs',
    )
    op.drop_table('processing_jobs')
