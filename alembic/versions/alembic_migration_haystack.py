"""add haystack columns to files

Revision ID: a1b2c3d4e5f6
Revises: (nahraď ID poslední existující migrace)
Create Date: 2025-01-01 00:00:00.000000

Použití:
    alembic upgrade head
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "2f64dc3e7d4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Přidáme sloupce pro Haystack lokaci souboru
    op.add_column("files", sa.Column("volume_id", sa.Integer(), nullable=True))
    op.add_column("files", sa.Column("haystack_offset", sa.Integer(), nullable=True))
    op.add_column("files", sa.Column("haystack_size", sa.Integer(), nullable=True))
    # Status pro eventual consistency: "uploading" | "ready"
    op.add_column(
        "files",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="ready",  # existující záznamy jsou "ready" (lokální disk)
        ),
    )


def downgrade() -> None:
    op.drop_column("files", "status")
    op.drop_column("files", "haystack_size")
    op.drop_column("files", "haystack_offset")
    op.drop_column("files", "volume_id")