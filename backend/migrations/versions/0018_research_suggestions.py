"""Learning Research suggestions; no source changes or backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Frozen definitions, independent of mutable application metadata.
metadata = sa.MetaData(schema="admin")

research_query_suggestion = sa.Table(
    "research_query_suggestion",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("normalized_query", sa.String(300), nullable=False, unique=True),
    sa.Column("display_query", sa.String(300), nullable=False),
    sa.Column("language", sa.String(16), nullable=False),
    sa.Column("search_prefixes", sa.ARRAY(sa.Text), nullable=False),
    sa.Column("success_count", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("suggestion_impressions", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("suggestion_selections", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("successful_selections", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_selected_at", sa.DateTime(timezone=True)),
    sa.Column("is_eligible", sa.Boolean, nullable=False),
    sa.Column("is_blocked", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.CheckConstraint(
        "success_count >= 0 AND suggestion_impressions >= 0 AND "
        "suggestion_selections >= 0 AND successful_selections >= 0",
        name="research_suggestion_counts",
    ),
)
sa.Index(
    "research_suggestion_prefix_idx",
    research_query_suggestion.c.search_prefixes,
    postgresql_using="gin",
    postgresql_where=sa.text("is_eligible AND NOT is_blocked"),
)
sa.Index(
    "research_suggestion_language_used_idx",
    research_query_suggestion.c.language,
    research_query_suggestion.c.last_used_at,
)

research_query_history = sa.Table(
    "research_query_history",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    # Rejected text is never retained, even in history.
    sa.Column("query_text", sa.String(300)),
    sa.Column("normalized_query", sa.String(300)),
    sa.Column("language", sa.String(16), nullable=False),
    sa.Column("domain", sa.String(160)),
    sa.Column("intent", sa.String(160)),
    sa.Column("entity_type", sa.String(160)),
    sa.Column("metric", sa.String(160)),
    sa.Column("area_query", sa.String(160)),
    sa.Column("suggestion_id", UUID, sa.ForeignKey("admin.research_query_suggestion.id")),
    sa.Column("suggestion_request_id", UUID),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("successful", sa.Boolean, nullable=False),
    sa.Column("is_eligible", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("suggestion_request_id", "suggestion_id", name="research_conversion_once"),
    sa.CheckConstraint(
        "source IN ('direct','suggestion') AND successful", name="research_history_success"
    ),
    sa.CheckConstraint(
        "is_eligible OR (query_text IS NULL AND normalized_query IS NULL AND area_query IS NULL)",
        name="research_history_redacted",
    ),
)
sa.Index("research_history_created_idx", research_query_history.c.created_at)

research_query_suggestion_event = sa.Table(
    "research_query_suggestion_event",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "suggestion_id", UUID, sa.ForeignKey("admin.research_query_suggestion.id"), nullable=False
    ),
    sa.Column("request_id", UUID, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("prefix", sa.String(120)),
    sa.Column("position", sa.SmallInteger, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("request_id", "suggestion_id", "event_type", name="research_event_once"),
    sa.CheckConstraint("event_type IN ('impression','selection')", name="research_event_type"),
    sa.CheckConstraint("position BETWEEN 1 AND 8", name="research_event_position"),
)
sa.Index("research_event_created_idx", research_query_suggestion_event.c.created_at)


def upgrade() -> None:
    metadata.create_all(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    # Explicit downgrade removes only the new learning history and aggregates.
    metadata.drop_all(op.get_bind(), checkfirst=False)
