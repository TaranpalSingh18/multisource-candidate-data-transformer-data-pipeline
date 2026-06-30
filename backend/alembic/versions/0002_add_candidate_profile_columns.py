"""Add profile and overall_confidence to candidates

Revision ID: 0002_add_candidate_profile
Revises: 0001_initial
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_candidate_profile"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("profile", sa.JSON(), nullable=True))
    op.add_column(
        "candidates",
        sa.Column("overall_confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "overall_confidence")
    op.drop_column("candidates", "profile")

