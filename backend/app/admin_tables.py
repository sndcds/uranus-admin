"""Only admin-owned metadata. Never reflect or model Uranus tables here."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.geo_types import Geometry

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

# Admin ownership is independent of Uranus users. Task identity is either one
# persisted finding or one explicitly typed workflow record.
assignment = sa.Table(
    "assignment",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "finding_id",
        sa.Text,
        sa.ForeignKey("admin.finding.id", ondelete="RESTRICT"),
    ),
    sa.Column("workflow_type", sa.Text),
    sa.Column("workflow_key", sa.Text),
    sa.Column("entity_type", sa.Text, nullable=False),
    sa.Column("entity_key", sa.Text, nullable=False),
    sa.Column(
        "assigned_to_admin_id",
        UUID,
        sa.ForeignKey("admin.auth_account.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("assigned_by_subject", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("due_at", sa.DateTime(timezone=True)),
    sa.Column("snoozed_until", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("version", sa.Integer, nullable=False),
    sa.CheckConstraint(
        "(finding_id IS NOT NULL AND workflow_type IS NULL AND workflow_key IS NULL) OR "
        "(finding_id IS NULL AND workflow_type IS NOT NULL AND workflow_key IS NOT NULL)",
        name="assignment_task_identity",
    ),
    sa.CheckConstraint(
        "status IN ('open','in_progress','done','cancelled')", name="assignment_status"
    ),
    sa.CheckConstraint("version >= 1", name="assignment_version"),
    sa.CheckConstraint(
        "(status IN ('done','cancelled') AND completed_at IS NOT NULL) OR "
        "(status IN ('open','in_progress') AND completed_at IS NULL)",
        name="assignment_completion",
    ),
)
sa.Index(
    "assignment_active_finding_idx",
    assignment.c.finding_id,
    unique=True,
    postgresql_where=assignment.c.status.in_(["open", "in_progress"]),
)
sa.Index(
    "assignment_active_workflow_idx",
    assignment.c.workflow_type,
    assignment.c.workflow_key,
    unique=True,
    postgresql_where=assignment.c.status.in_(["open", "in_progress"]),
)
sa.Index(
    "assignment_assignee_status_due_idx",
    assignment.c.assigned_to_admin_id,
    assignment.c.status,
    assignment.c.due_at,
    assignment.c.id,
)

assignment_event = sa.Table(
    "assignment_event",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "assignment_id",
        UUID,
        sa.ForeignKey("admin.assignment.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("assigned_to_admin_id", UUID, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("due_at", sa.DateTime(timezone=True)),
    sa.Column("snoozed_until", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("assignment_id", "version", name="assignment_event_version"),
    sa.CheckConstraint(
        "kind IN ('created','updated','completed','reopened','cancelled')",
        name="assignment_event_kind",
    ),
    sa.CheckConstraint(
        "status IN ('open','in_progress','done','cancelled')",
        name="assignment_event_status",
    ),
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
sa.Index("notification_entity_idx", notification.c.entity_type, notification.c.entity_key)
sa.Index(
    "notification_type_detected_idx",
    notification.c.notification_type,
    notification.c.last_detected_at,
)

notification_delivery = sa.Table(
    "notification_delivery",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "retry_of_delivery_id",
        UUID,
        sa.ForeignKey(
            "admin.notification_delivery.id",
            ondelete="RESTRICT",
            name="notification_delivery_retry_of_fk",
        ),
    ),
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

# One non-cancelled direct successor; obsolete cancelled intents keep their history.
sa.Index(
    "notification_delivery_retry_of_idx",
    notification_delivery.c.retry_of_delivery_id,
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

# Cache metadata is separate from authoritative Uranus points.
geo_area = sa.Table(
    "geo_area",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("source_id", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("country_code", sa.Text),
    sa.Column("admin_level", sa.Integer),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("provider_class", sa.Text),
    sa.Column("provider_type", sa.Text),
    sa.Column("provider_addresstype", sa.Text),
    sa.Column("geometry", Geometry("MultiPolygon"), nullable=False),
    sa.Column("bbox", Geometry("Polygon")),
    sa.Column("hierarchy", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source", "source_type", "source_id", name="geo_area_source_identity"),
    sa.CheckConstraint(
        "kind IN ('country','region','county','municipality','city','district','other')",
        name="geo_area_kind",
    ),
    sa.CheckConstraint(
        "NOT ST_IsEmpty(geometry) AND ST_IsValid(geometry)", name="geo_area_geometry_valid"
    ),
)
sa.Index("geo_area_geometry_idx", geo_area.c.geometry, postgresql_using="gist")
sa.Index("geo_area_country_code_idx", geo_area.c.country_code)
sa.Index("geo_area_kind_idx", geo_area.c.kind)
sa.Index("geo_area_fetched_at_idx", geo_area.c.fetched_at)

geocode_request = sa.Table(
    "geocode_request",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("entity_type", sa.Text, nullable=False),
    sa.Column("entity_key", UUID, nullable=False),
    sa.Column("source_fingerprint", sa.Text, nullable=False),
    sa.Column("query_fingerprint", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("generation", sa.Integer, nullable=False, server_default="1"),
    sa.Column("query_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("scoring_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("checked_at", sa.DateTime(timezone=True)),
    sa.Column("next_check_at", sa.DateTime(timezone=True)),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_error", sa.Text),
    sa.Column("worker_id", UUID),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("entity_type", "entity_key", name="geocode_request_entity"),
    sa.CheckConstraint(
        "entity_type IN ('organization','venue')", name="geocode_request_entity_type"
    ),
    sa.CheckConstraint(
        "status IN ('pending','checking','candidate','ambiguous','not_found',"
        "'insufficient_input','failed','stale')",
        name="geocode_request_status",
    ),
    sa.CheckConstraint(
        "generation > 0 AND query_version > 0 AND scoring_version > 0 AND attempt_count >= 0",
        name="geocode_request_versions",
    ),
    sa.CheckConstraint(
        "source_fingerprint ~ '^[0-9a-f]{64}$' AND query_fingerprint ~ '^[0-9a-f]{64}$'",
        name="geocode_request_fingerprints",
    ),
    sa.CheckConstraint(
        "last_error IS NULL OR last_error = 'provider_unavailable'", name="geocode_request_error"
    ),
    sa.CheckConstraint(
        "(status = 'checking' AND worker_id IS NOT NULL AND lease_until IS NOT NULL) "
        "OR (status <> 'checking' AND worker_id IS NULL AND lease_until IS NULL)",
        name="geocode_request_lease",
    ),
)
sa.Index(
    "geocode_request_due_idx",
    geocode_request.c.status,
    geocode_request.c.next_check_at,
    geocode_request.c.id,
)
sa.Index(
    "geocode_request_lease_idx",
    geocode_request.c.lease_until,
    postgresql_where=geocode_request.c.status == "checking",
)

geocode_candidate = sa.Table(
    "geocode_candidate",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "request_id",
        UUID,
        sa.ForeignKey("admin.geocode_request.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("rank", sa.Integer, nullable=False),
    sa.Column("source_fingerprint", sa.Text, nullable=False),
    sa.Column("query_fingerprint", sa.Text, nullable=False),
    sa.Column("query_version", sa.Integer, nullable=False),
    sa.Column("scoring_version", sa.Integer, nullable=False),
    sa.Column("latitude", sa.Double, nullable=False),
    sa.Column("longitude", sa.Double, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("osm_type", sa.Text),
    sa.Column("osm_id", sa.Text),
    sa.Column("provider_class", sa.Text),
    sa.Column("provider_type", sa.Text),
    sa.Column("provider_addresstype", sa.Text),
    sa.Column("provider_importance", sa.Double),
    sa.Column("match_score", sa.Double, nullable=False),
    sa.Column("match_reasons", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("address", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("request_id", "generation", "rank", name="geocode_candidate_rank"),
    sa.CheckConstraint(
        "generation > 0 AND rank BETWEEN 1 AND 5", name="geocode_candidate_generation_rank"
    ),
    sa.CheckConstraint(
        "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
        name="geocode_candidate_coordinates",
    ),
    sa.CheckConstraint("match_score BETWEEN 0 AND 1", name="geocode_candidate_score"),
    sa.CheckConstraint(
        "provider_importance IS NULL OR (provider_importance > '-Infinity'::float8 "
        "AND provider_importance < 'Infinity'::float8)",
        name="geocode_candidate_importance",
    ),
    sa.CheckConstraint(
        "osm_type IS NULL OR osm_type IN ('node','way','relation')",
        name="geocode_candidate_osm_type",
    ),
    sa.CheckConstraint(
        "osm_id IS NULL OR osm_id ~ '^[1-9][0-9]{0,18}$'", name="geocode_candidate_osm_id"
    ),
    sa.CheckConstraint(
        "jsonb_typeof(address) = 'object' AND jsonb_typeof(match_reasons) = 'array'",
        name="geocode_candidate_json",
    ),
    sa.CheckConstraint("length(display_name) BETWEEN 1 AND 1024", name="geocode_candidate_name"),
)
