"""add billing columns to bucket

Revision ID: ec4f208bd878
Revises: 2f64dc3e7d4c
Create Date: 2026-04-16 12:17:23.005387

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ec4f208bd878"
down_revision: Union[str, Sequence[str], None] = "2f64dc3e7d4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "buckets",
        sa.Column(
            "bandwidth_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "buckets",
        sa.Column(
            "current_storage_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "buckets",
        sa.Column(
            "ingress_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "buckets",
        sa.Column(
            "egress_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "buckets",
        sa.Column(
            "internal_transfer_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("buckets", "internal_transfer_bytes")
    op.drop_column("buckets", "egress_bytes")
    op.drop_column("buckets", "ingress_bytes")
    op.drop_column("buckets", "current_storage_bytes")
    op.drop_column("buckets", "bandwidth_bytes")
