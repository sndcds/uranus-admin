"""Explicit research grant, independent of the system administrator grant.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_journalist",
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
        schema="admin",
    )


def downgrade() -> None:
    # Explicit rollback removes journalist grants; accounts and sessions are preserved.
    op.drop_table("auth_journalist", schema="admin")
