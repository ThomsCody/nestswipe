"""Index sent household invitations by inviter and newest first.

Revision ID: 021
Revises: 020
"""

import sqlalchemy as sa
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires concurrent index operations outside a transaction.
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_household_invites_inviter_id_created_at",
            "household_invites",
            ["inviter_id", sa.text("created_at DESC")],
            schema="public",
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_household_invites_inviter_id_created_at",
            table_name="household_invites",
            schema="public",
            postgresql_concurrently=True,
        )
