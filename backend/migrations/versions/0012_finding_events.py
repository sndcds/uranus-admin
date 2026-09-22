"""Append-only finding lifecycle events for entity timelines."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

metadata = sa.MetaData(schema="admin")

sa.Table("finding", metadata, sa.Column("id", sa.Text, primary_key=True))

finding_event = sa.Table(
    "finding_event",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "finding_id",
        sa.Text,
        sa.ForeignKey("admin.finding.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("entity_type", sa.Text, nullable=False),
    sa.Column("entity_key", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.Text),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("rule", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("field", sa.Text, nullable=False),
    sa.Column("message", sa.Text, nullable=False),
    sa.Column("comment", sa.Text),
    sa.Column("assigned_to", UUID),
    sa.Column("snoozed_until", sa.DateTime(timezone=True)),
    sa.Column("exception_reason", sa.Text),
    sa.CheckConstraint(
        "kind IN ('detected','reviewed','reopened','resolved')", name="finding_event_kind"
    ),
    sa.CheckConstraint(
        "status IN ('open','in_progress','snoozed','exception','reviewed','ignored','resolved')",
        name="finding_event_status",
    ),
    sa.CheckConstraint("severity IN ('error','warning','info')", name="finding_event_severity"),
)
sa.Index(
    "finding_event_entity_timeline_idx",
    finding_event.c.entity_type,
    finding_event.c.entity_key,
    finding_event.c.occurred_at.desc(),
    finding_event.c.id.desc(),
)
sa.Index("finding_event_finding_idx", finding_event.c.finding_id, finding_event.c.occurred_at)


def upgrade() -> None:
    finding_event.create(op.get_bind())
    op.create_index(
        "notification_entity_idx",
        "notification",
        ["entity_type", "entity_key"],
        schema="admin",
    )
    columns = """id,finding_id,entity_type,entity_key,kind,occurred_at,actor,status,
        rule,severity,field,message,comment,assigned_to,snoozed_until,exception_reason"""
    op.execute(
        sa.text(
            f"""INSERT INTO admin.finding_event ({columns})
            SELECT md5('uranus-admin:finding-event:' || id || ':detected:' ||
                       first_seen_at::text)::uuid,
                   id,entity_type,entity_id,'detected',first_seen_at,NULL,'open',
                   rule,severity,field,message,comment,assigned_to,snoozed_until,exception_reason
            FROM admin.finding"""
        )
    )
    op.execute(
        sa.text(
            f"""INSERT INTO admin.finding_event ({columns})
            SELECT md5('uranus-admin:finding-event:' || id || ':reviewed:' ||
                       reviewed_at::text)::uuid,
                   id,entity_type,entity_id,'reviewed',reviewed_at,reviewed_subject,status,
                   rule,severity,field,message,comment,assigned_to,snoozed_until,exception_reason
            FROM admin.finding WHERE reviewed_at IS NOT NULL"""
        )
    )
    op.execute(
        sa.text(
            f"""INSERT INTO admin.finding_event ({columns})
            SELECT md5('uranus-admin:finding-event:' || id || ':resolved:' ||
                       resolved_at::text)::uuid,
                   id,entity_type,entity_id,'resolved',resolved_at,NULL,'resolved',
                   rule,severity,field,message,comment,assigned_to,snoozed_until,exception_reason
            FROM admin.finding WHERE resolved_at IS NOT NULL"""
        )
    )


def downgrade() -> None:
    op.drop_index("notification_entity_idx", table_name="notification", schema="admin")
    finding_event.drop(op.get_bind())
