"""add llm token columns to parse_attempts

Revision ID: 017
Revises: 016
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parse_attempts", sa.Column("llm_input_tokens", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("llm_output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("parse_attempts", "llm_output_tokens")
    op.drop_column("parse_attempts", "llm_input_tokens")
