"""add problem is_public

Revision ID: b0e9c1f4a7d1
Revises: a46404eabb2f
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0e9c1f4a7d1'
down_revision: Union[str, Sequence[str], None] = 'a46404eabb2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_public boolean column to problems (default true for existing rows)."""
    op.add_column(
        "problems",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("problems", "is_public")
