"""Add independent administrator task assignments."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

metadata = sa.MetaData(schema="admin")
sa.Table("finding", metadata, sa.Column("id", sa.Text, primary_key=True))
sa.Table("auth_account", metadata, sa.Column("id", UUID, primary_key=True))

assignment = sa.Table(
    "assignment",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("finding_id", sa.Text, sa.ForeignKey("admin.finding.id", ondelete="RESTRICT")),
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


def upgrade() -> None:
    assignment.create(op.get_bind())
    assignment_event.create(op.get_bind())


def downgrade() -> None:
    assignment_event.drop(op.get_bind())
    assignment.drop(op.get_bind())
