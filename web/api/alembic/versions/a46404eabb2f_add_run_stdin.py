"""add run stdin

Revision ID: a46404eabb2f
Revises: fc1fd6c4afd9
Create Date: 2026-09-06 08:57:16.641211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a46404eabb2f'
down_revision: Union[str, Sequence[str], None] = 'fc1fd6c4afd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("stdin", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "stdin")
