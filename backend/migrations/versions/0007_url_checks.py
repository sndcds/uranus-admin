"""Persist bounded asynchronous URL observations. Downgrade loses these observations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "url_check",
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
            "next_check_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("worker_id", UUID),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_type", "source_key", "field", name="url_check_source"),
        schema="admin",
    )
    op.create_index("url_check_due_idx", "url_check", ["next_check_at"], schema="admin")


def downgrade() -> None:
    op.drop_index("url_check_due_idx", table_name="url_check", schema="admin")
    op.drop_table("url_check", schema="admin")
