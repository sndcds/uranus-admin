"""Cache administrative boundaries in admin only. PostGIS must already be provisioned."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.geo_types import Geometry

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_area",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("country_code", sa.Text),
        sa.Column("admin_level", sa.Integer),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("provider_class", sa.Text),
        sa.Column("provider_type", sa.Text),
        sa.Column("provider_addresstype", sa.Text),
        sa.Column("geometry", Geometry("MultiPolygon"), nullable=False),
        sa.Column("bbox", Geometry("Polygon")),
        sa.Column("hierarchy", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_type", "source_id", name="geo_area_source_identity"),
        sa.CheckConstraint(
            "kind IN ('country','region','county','municipality','city','district','other')",
            name="geo_area_kind",
        ),
        sa.CheckConstraint(
            "NOT ST_IsEmpty(geometry) AND ST_IsValid(geometry)", name="geo_area_geometry_valid"
        ),
        schema="admin",
    )
    op.create_index(
        "geo_area_geometry_idx", "geo_area", ["geometry"], schema="admin", postgresql_using="gist"
    )
    for column in ("country_code", "kind", "fetched_at"):
        op.create_index(f"geo_area_{column}_idx", "geo_area", [column], schema="admin")


def downgrade() -> None:
    op.drop_table("geo_area", schema="admin")
