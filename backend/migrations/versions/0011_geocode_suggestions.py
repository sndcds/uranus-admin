"""Immutable generations of location suggestions; admin only."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None
metadata = sa.MetaData(schema="admin")

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


def upgrade() -> None:
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    op.drop_table("geocode_candidate", schema="admin")
    op.drop_table("geocode_request", schema="admin")
