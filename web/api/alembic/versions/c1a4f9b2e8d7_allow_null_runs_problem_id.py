"""allow null problem_id on runs

Revision ID: c1a4f9b2e8d7
Revises: b0e9c1f4a7d1
Create Date: 2026-09-07 19:05:00.000000

Practice/sandbox mode (free-form exploration, no grading) was added in
todo 30 but the run creation endpoint still required ``problem_id``.  The
frontend ``/practice`` tab now lets the student write code without picking
a problem, and the API has to accept ``problem_id: null`` for that flow.

This migration makes ``runs.problem_id`` nullable and drops the foreign
key constraint (the engine judges whatever source the student submits
and doesn't need a problem record for the scratch flow).  Graded modes
(``assignment`` and ``contest``) still require a real ``problem_id`` —
enforced at the API layer in ``routes/runs.py``.

The ``test_results.problem_id`` column is **not** touched: per-case test
result rows always belong to a known problem.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a4f9b2e8d7"
down_revision: Union[str, Sequence[str], None] = "b0e9c1f4a7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "runs_problem_id_fkey",
        "runs",
        type_="foreignkey",
    )
    op.alter_column(
        "runs",
        "problem_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "runs",
        "problem_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "runs_problem_id_fkey",
        "runs",
        "problems",
        ["problem_id"],
        ["id"],
    )
