"""Append-only manual delivery retries; retain all existing delivery history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_delivery",
        sa.Column("retry_of_delivery_id", UUID, nullable=True),
        schema="admin",
    )
    op.create_foreign_key(
        "notification_delivery_retry_of_fk",
        "notification_delivery",
        "notification_delivery",
        ["retry_of_delivery_id"],
        ["id"],
        source_schema="admin",
        referent_schema="admin",
        ondelete="RESTRICT",
    )
    op.create_index(
        "notification_delivery_retry_of_idx",
        "notification_delivery",
        ["retry_of_delivery_id"],
        unique=True,
        schema="admin",
        postgresql_where=sa.text("status != 'cancelled'"),
    )


def downgrade() -> None:
    op.drop_index(
        "notification_delivery_retry_of_idx", table_name="notification_delivery", schema="admin"
    )
    op.drop_constraint(
        "notification_delivery_retry_of_fk",
        "notification_delivery",
        schema="admin",
        type_="foreignkey",
    )
    op.drop_column("notification_delivery", "retry_of_delivery_id", schema="admin")
