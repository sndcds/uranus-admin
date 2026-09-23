"""Add organizational snooze timestamps and append-only event snapshots.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("assignment", "assignment_event"):
        op.add_column(table, sa.Column("snoozed_until", sa.DateTime(timezone=True)), schema="admin")


def downgrade() -> None:
    # Explicit rollback loses snooze metadata, but preserves all versions and event rows.
    for table in ("assignment_event", "assignment"):
        op.drop_column(table, "snoozed_until", schema="admin")
