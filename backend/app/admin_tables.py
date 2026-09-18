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
    sa.Column("worker_id", UUID),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("rule_results", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.CheckConstraint(
        "status IN ('queued', 'running', 'success', 'failed')", name="check_run_status"
    ),
    sa.CheckConstraint("rule_count >= 0 AND finding_count >= 0", name="check_run_counts"),
    sa.CheckConstraint("finished_at >= started_at", name="check_run_timestamps"),
)

sa.Index(
    "check_run_one_active_idx",
    sa.literal_column("(true)"),
    unique=True,
    postgresql_where=check_run.c.status.in_(["queued", "running"]),
    _table=check_run,
)

finding = sa.Table(
    "finding",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("rule", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("entity_type", sa.Text, nullable=False),
    # Text deliberately supports composite domain keys, without cross-schema foreign keys.
    sa.Column("entity_id", sa.Text, key="entity_key", nullable=False),
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
    sa.Column("assigned_to", UUID),
    sa.Column("reviewed_subject", sa.Text),
    sa.Column("snoozed_until", sa.DateTime(timezone=True)),
    sa.Column("exception_reason", sa.Text),
    sa.UniqueConstraint("rule", "entity_type", "entity_key", "field", name="finding_identity"),
    sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="finding_severity"),
    sa.CheckConstraint(
        "status IN ('open','in_progress','snoozed','exception','reviewed','ignored','resolved')",
        name="finding_status",
    ),
    sa.CheckConstraint("last_seen_at >= first_seen_at", name="finding_timestamps"),
)
sa.Index("finding_status_rule_idx", finding.c.status, finding.c.rule)

record_mark = sa.Table(
    "record_mark",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("entity_type", sa.Text, nullable=False),
    sa.Column("entity_key", sa.Text, nullable=False),
    sa.Column("entity_name", sa.Text, nullable=False),
    sa.Column("reasons", JSONB, nullable=False),
    sa.Column("reason_detail", sa.Text),
    sa.Column("urgency", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("completed_by", sa.Text),
    sa.CheckConstraint("status IN ('open','in_progress','done')", name="record_mark_status"),
    sa.CheckConstraint("urgency IN ('normal','high','urgent')", name="record_mark_urgency"),
    sa.CheckConstraint("version >= 1", name="record_mark_version"),
    sa.CheckConstraint(
        "(status = 'done' AND completed_at IS NOT NULL AND completed_by IS NOT NULL) OR "
        "(status <> 'done' AND completed_at IS NULL AND completed_by IS NULL)",
        name="record_mark_completion",
    ),
)
sa.Index("record_mark_entity_idx", record_mark.c.entity_type, record_mark.c.entity_key)
sa.Index("record_mark_status_urgency_idx", record_mark.c.status, record_mark.c.urgency)

record_mark_event = sa.Table(
    "record_mark_event",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("mark_id", UUID, sa.ForeignKey("admin.record_mark.id"), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("author", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("reasons", JSONB, nullable=False),
    sa.Column("reason_detail", sa.Text),
    sa.Column("urgency", sa.Text, nullable=False),
    sa.UniqueConstraint("mark_id", "version", name="record_mark_event_version"),
    sa.CheckConstraint(
        "kind IN ('created','updated','completed','reopened')", name="record_mark_event_kind"
    ),
)

# Authentication is independent of Uranus accounts and organizational permissions.
auth_account = sa.Table(
    "auth_account",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("login", sa.Text, nullable=False, unique=True),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("credential_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.CheckConstraint("credential_version >= 1", name="auth_account_version"),
)
auth_system_admin = sa.Table(
    "auth_system_admin",
    metadata,
    sa.Column(
        "account_id",
        UUID,
        sa.ForeignKey("admin.auth_account.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("granted_by", sa.Text, nullable=False),
)
auth_session = sa.Table(
    "auth_session",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column(
        "account_id",
        UUID,
        sa.ForeignKey("admin.auth_account.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("credential_version", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint("expires_at > created_at", name="auth_session_lifetime"),
)
sa.Index("auth_session_account_idx", auth_session.c.account_id)
sa.Index("auth_session_expiry_idx", auth_session.c.expires_at)
auth_login_bucket = sa.Table(
    "auth_login_bucket",
    metadata,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
    sa.CheckConstraint("attempts > 0", name="auth_login_bucket_attempts"),
)

sa.Index("auth_session_idle_idx", auth_session.c.last_seen_at)
sa.Index("auth_session_revoked_idx", auth_session.c.revoked_at)
sa.Index("auth_login_bucket_expiry_idx", auth_login_bucket.c.window_end)


url_check = sa.Table(
    "url_check",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("source_key", sa.Text, nullable=False),
    sa.Column("field", sa.Text, nullable=False),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("last_checked_at", sa.DateTime(timezone=True)),
    sa.Column("last_success_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("status_code", sa.Integer),
    sa.Column("redirect_target", sa.Text),
    sa.Column("failure_type", sa.Text),
    sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column(
        "next_check_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("worker_id", UUID),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("source_type", "source_key", "field", name="url_check_source"),
)
sa.Index("url_check_due_idx", url_check.c.next_check_at)

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
