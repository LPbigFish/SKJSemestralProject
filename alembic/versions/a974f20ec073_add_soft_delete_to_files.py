"""add soft delete to files

Revision ID: a974f20ec073
Revises: ec4f208bd878
Create Date: 2026-04-16 12:18:53.202451

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a974f20ec073"
down_revision: Union[str, Sequence[str], None] = "ec4f208bd878"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "files",
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("files", "is_deleted")
