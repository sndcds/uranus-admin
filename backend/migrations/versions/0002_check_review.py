"""Persist rule coverage and human review metadata in admin only."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "check_run",
        sa.Column("rule_results", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="admin",
    )
    op.add_column("finding", sa.Column("assigned_to", UUID), schema="admin")
    op.add_column("finding", sa.Column("reviewed_subject", sa.Text), schema="admin")
    op.add_column("finding", sa.Column("snoozed_until", sa.DateTime(timezone=True)), schema="admin")
    op.add_column("finding", sa.Column("exception_reason", sa.Text), schema="admin")
    op.drop_constraint("finding_status", "finding", schema="admin", type_="check")
    op.create_check_constraint(
        "finding_status",
        "finding",
        "status IN ('open','in_progress','snoozed','exception','reviewed','ignored','resolved')",
        schema="admin",
    )


def downgrade() -> None:
    # Preserve visibility of states the old application does not understand.
    op.execute(
        "UPDATE admin.finding SET status='open' "
        "WHERE status IN ('in_progress','snoozed','exception')"
    )
    op.drop_constraint("finding_status", "finding", schema="admin", type_="check")
    op.create_check_constraint(
        "finding_status",
        "finding",
        "status IN ('open','reviewed','ignored','resolved')",
        schema="admin",
    )
    for column in ("assigned_to", "reviewed_subject", "snoozed_until", "exception_reason"):
        op.drop_column("finding", column, schema="admin")
    op.drop_column("check_run", "rule_results", schema="admin")
