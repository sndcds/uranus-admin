"""Durable notifications and immutable delivery audit, admin only.

Runtime grants are provisioned separately, as in all preceding revisions.
Downgrade explicitly destroys notification history.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None
metadata = sa.MetaData(schema="admin")

notification = sa.Table(
    "notification",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("notification_type", sa.Text, nullable=False),
    sa.Column("organization_id", UUID, nullable=False),
    sa.Column("entity_type", sa.Text),
    sa.Column("entity_key", sa.Text),
    sa.Column("entity_name", sa.Text),
    sa.Column("finding_id", sa.Text),
    sa.Column("rule", sa.Text),
    sa.Column("dedupe_key", sa.Text, nullable=False, unique=True),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True)),
    sa.Column("expired_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "notification_type IN ('unpublished_upcoming_event','quality_finding')",
        name="notification_type",
    ),
    sa.CheckConstraint(
        "status IN ('pending','active','resolved','suppressed','expired')",
        name="notification_status",
    ),
)
sa.Index("notification_org_status_idx", notification.c.organization_id, notification.c.status)
sa.Index(
    "notification_type_detected_idx",
    notification.c.notification_type,
    notification.c.last_detected_at,
)

notification_delivery = sa.Table(
    "notification_delivery",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("organization_id", UUID, nullable=False),
    sa.Column("recipient", sa.Text, nullable=False),
    sa.Column("locale", sa.Text, nullable=False),
    sa.Column("channel", sa.Text, nullable=False, server_default="email"),
    sa.Column("delivery_kind", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("subject", sa.Text),
    sa.Column("message_fingerprint", sa.Text, nullable=False),
    # Immutable intent + content snapshot; retries retain the same RFC Message-ID and body.
    sa.Column("snapshot", JSONB, nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("queued_at", sa.DateTime(timezone=True)),
    sa.Column("sending_at", sa.DateTime(timezone=True)),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    sa.Column("worker_id", UUID),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("last_error", sa.Text),
    sa.Column("provider_message_id", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("locale IN ('de','da','en')", name="notification_delivery_locale"),
    sa.CheckConstraint("channel = 'email'", name="notification_delivery_channel"),
    sa.CheckConstraint(
        "delivery_kind IN ('initial','reminder','escalation','digest','test')",
        name="notification_delivery_kind",
    ),
    sa.CheckConstraint(
        "status IN ('queued','sending','sent','failed','permanent_failure','cancelled')",
        name="notification_delivery_status",
    ),
    sa.CheckConstraint("attempt_count BETWEEN 0 AND 5", name="notification_delivery_attempts"),
)
sa.Index(
    "notification_delivery_due_idx",
    notification_delivery.c.status,
    notification_delivery.c.next_attempt_at,
)
sa.Index(
    "notification_delivery_recipient_sent_idx",
    notification_delivery.c.recipient,
    notification_delivery.c.sent_at,
)
sa.Index("notification_delivery_org_idx", notification_delivery.c.organization_id)
sa.Index(
    "notification_delivery_fingerprint_idx",
    notification_delivery.c.message_fingerprint,
    unique=True,
    postgresql_where=notification_delivery.c.status != "cancelled",
)

notification_delivery_item = sa.Table(
    "notification_delivery_item",
    metadata,
    sa.Column(
        "delivery_id",
        UUID,
        sa.ForeignKey("admin.notification_delivery.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "notification_id",
        UUID,
        sa.ForeignKey("admin.notification.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)
sa.Index(
    "notification_delivery_item_notification_idx", notification_delivery_item.c.notification_id
)


def upgrade() -> None:
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    metadata.drop_all(op.get_bind(), checkfirst=False)
