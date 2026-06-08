"""add parse_attempts table

Revision ID: 015
Revises: 014
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parse_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("email_id", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("fail_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_parse_attempts_id"), "parse_attempts", ["id"], unique=False)
    op.create_index(op.f("ix_parse_attempts_household_id"), "parse_attempts", ["household_id"], unique=False)
    op.create_index(op.f("ix_parse_attempts_created_at"), "parse_attempts", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_parse_attempts_created_at"), table_name="parse_attempts")
    op.drop_index(op.f("ix_parse_attempts_household_id"), table_name="parse_attempts")
    op.drop_index(op.f("ix_parse_attempts_id"), table_name="parse_attempts")
    op.drop_table("parse_attempts")
