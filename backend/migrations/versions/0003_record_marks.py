"""Independent record marks with append-only application history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

metadata = sa.MetaData(schema="admin")

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


def upgrade() -> None:
    record_mark.create(op.get_bind())
    record_mark_event.create(op.get_bind())


def downgrade() -> None:
    record_mark_event.drop(op.get_bind())
    record_mark.drop(op.get_bind())
