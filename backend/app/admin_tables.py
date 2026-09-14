"""Only admin-owned metadata. Never reflect or model Uranus tables here."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = sa.MetaData(schema="admin")

check_run = sa.Table(
    "check_run",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("rule_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("finding_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("error_message", sa.Text),
    sa.CheckConstraint("status IN ('running', 'success', 'failed')", name="check_run_status"),
    sa.CheckConstraint("rule_count >= 0 AND finding_count >= 0", name="check_run_counts"),
    sa.CheckConstraint("finished_at >= started_at", name="check_run_timestamps"),
)

finding = sa.Table(
    "finding",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("rule", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("entity_type", sa.Text, nullable=False),
    # Text deliberately supports composite domain keys, without cross-schema foreign keys.
    sa.Column("entity_id", sa.Text, nullable=False),
    sa.Column("field", sa.Text, nullable=False, server_default=""),
    sa.Column("message", sa.Text, nullable=False),
    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True)),
    sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("status", sa.Text, nullable=False, server_default="open"),
    sa.Column("reviewed_by", UUID),
    sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    sa.Column("ignored_until", sa.DateTime(timezone=True)),
    sa.Column("comment", sa.Text),
    sa.UniqueConstraint("rule", "entity_type", "entity_id", "field", name="finding_identity"),
    sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="finding_severity"),
    sa.CheckConstraint(
        "status IN ('open', 'reviewed', 'ignored', 'resolved')", name="finding_status"
    ),
    sa.CheckConstraint("last_seen_at >= first_seen_at", name="finding_timestamps"),
)
sa.Index("finding_status_rule_idx", finding.c.status, finding.c.rule)
