"""Persist client activity and reserve an idle maintenance window.

Revision ID: 022
Revises: 021
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE maintenance_presence (
            id integer PRIMARY KEY CHECK (id = 1),
            last_activity timestamptz NOT NULL DEFAULT now(),
            reboot_until timestamptz
        )
    """)
    op.execute("INSERT INTO maintenance_presence (id) VALUES (1)")


def downgrade():
    op.drop_table("maintenance_presence")
