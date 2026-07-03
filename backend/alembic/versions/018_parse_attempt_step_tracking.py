"""add per-step token/diagnostic columns to parse_attempts

Revision ID: 018
Revises: 017
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parse_attempts", sa.Column("call_type", sa.String(), nullable=True))
    op.add_column("parse_attempts", sa.Column("page_extraction_input_tokens", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("page_extraction_output_tokens", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("photo_classification_input_tokens", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("photo_classification_output_tokens", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("page_text_chars", sa.Integer(), nullable=True))
    op.add_column("parse_attempts", sa.Column("photo_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("parse_attempts", "photo_count")
    op.drop_column("parse_attempts", "page_text_chars")
    op.drop_column("parse_attempts", "photo_classification_output_tokens")
    op.drop_column("parse_attempts", "photo_classification_input_tokens")
    op.drop_column("parse_attempts", "page_extraction_output_tokens")
    op.drop_column("parse_attempts", "page_extraction_input_tokens")
    op.drop_column("parse_attempts", "call_type")
