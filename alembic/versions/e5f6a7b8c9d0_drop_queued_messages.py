"""drop queued_messages from gateway db

Revision ID: e5f6a7b8c9d0
Revises: fd02b873f286
Create Date: 2026-05-10 20:00:00.000000

The queued_messages table is now managed by the standalone broker service.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "fd02b873f286"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_queued_messages_topic", table_name="queued_messages")
    op.drop_table("queued_messages")


def downgrade() -> None:
    op.create_table(
        "queued_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_delivered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queued_messages_topic", "queued_messages", ["topic"], unique=False)
