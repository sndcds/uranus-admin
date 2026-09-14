"""Admin-owned storage only. No Uranus DDL and no application-time migration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "check_run",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint("status IN ('running', 'success', 'failed')", name="check_run_status"),
        sa.CheckConstraint("rule_count >= 0 AND finding_count >= 0", name="check_run_counts"),
        sa.CheckConstraint("finished_at >= started_at", name="check_run_timestamps"),
        schema="admin",
    )
    op.create_table(
        "finding",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("reviewed_by", postgresql.UUID()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("ignored_until", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.Text()),
        sa.UniqueConstraint("rule", "entity_type", "entity_id", "field", name="finding_identity"),
        sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="finding_severity"),
        sa.CheckConstraint(
            "status IN ('open', 'reviewed', 'ignored', 'resolved')", name="finding_status"
        ),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="finding_timestamps"),
        schema="admin",
    )
    op.create_index("finding_status_rule_idx", "finding", ["status", "rule"], schema="admin")


def downgrade() -> None:
    op.drop_index("finding_status_rule_idx", table_name="finding", schema="admin")
    op.drop_table("finding", schema="admin")
    op.drop_table("check_run", schema="admin")
