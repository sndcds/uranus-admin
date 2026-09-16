"""Durable queued checks with expiring, fenced worker leases."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stop old workers before deployment. Old running rows have no renewable lease.
    op.execute(
        "UPDATE admin.check_run SET status='failed', finished_at=clock_timestamp(), "
        "error_message='Interrupted during worker upgrade.' WHERE status='running'"
    )
    op.drop_constraint("check_run_status", "check_run", schema="admin")
    op.create_check_constraint(
        "check_run_status",
        "check_run",
        "status IN ('queued','running','success','failed')",
        schema="admin",
    )
    op.add_column("check_run", sa.Column("worker_id", UUID), schema="admin")
    op.add_column("check_run", sa.Column("lease_until", sa.DateTime(timezone=True)), schema="admin")
    op.create_index(
        "check_run_one_active_idx",
        "check_run",
        [sa.text("(true)")],
        unique=True,
        schema="admin",
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE admin.check_run SET status='failed', finished_at=clock_timestamp(), "
        "error_message='Interrupted during worker downgrade.' WHERE status IN ('queued','running')"
    )
    op.drop_index("check_run_one_active_idx", table_name="check_run", schema="admin")
    op.drop_column("check_run", "lease_until", schema="admin")
    op.drop_column("check_run", "worker_id", schema="admin")
    op.drop_constraint("check_run_status", "check_run", schema="admin")
    op.create_check_constraint(
        "check_run_status", "check_run", "status IN ('running','success','failed')", schema="admin"
    )
