"""Independent administrator accounts, explicit grants and revocable sessions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None
metadata = sa.MetaData(schema="admin")

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


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
