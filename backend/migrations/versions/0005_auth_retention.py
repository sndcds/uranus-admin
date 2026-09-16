"""Indexes for bounded authentication retention; no privilege changes."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("auth_session_idle_idx", "auth_session", ["last_seen_at"], schema="admin")
    op.create_index("auth_session_revoked_idx", "auth_session", ["revoked_at"], schema="admin")
    op.create_index(
        "auth_login_bucket_expiry_idx", "auth_login_bucket", ["window_end"], schema="admin"
    )


def downgrade() -> None:
    op.drop_index("auth_login_bucket_expiry_idx", table_name="auth_login_bucket", schema="admin")
    op.drop_index("auth_session_revoked_idx", table_name="auth_session", schema="admin")
    op.drop_index("auth_session_idle_idx", table_name="auth_session", schema="admin")
