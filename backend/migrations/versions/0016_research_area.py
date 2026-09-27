"""Operator-owned research boundary data; no source DDL or automatic grants."""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import UserDefinedType

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


class Geometry(UserDefinedType[bytes]):
    """Frozen spatial DDL for this revision."""

    cache_ok = True

    def __init__(self, shape: str):
        self.shape = shape

    def get_col_spec(self, **kw: Any) -> str:
        return f"geometry({self.shape},4326)"


def upgrade() -> None:
    op.create_table(
        "research_area",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("area_type", sa.Text, nullable=False),
        sa.Column("country_code", sa.Text, nullable=False),
        sa.Column("region_code", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("osm_type", sa.Text, nullable=False),
        sa.Column("osm_id", sa.BigInteger, nullable=False),
        sa.Column("osm_admin_level", sa.Integer, nullable=False),
        sa.Column("municipality_key", sa.Text),
        sa.Column("population_count", sa.Integer),
        sa.Column("population_date", sa.Date),
        sa.Column("population_source", sa.Text),
        sa.Column("population_name", sa.Text),
        sa.Column("population_file_sha256", sa.Text),
        sa.Column("population_imported_at", sa.DateTime(timezone=True)),
        sa.Column("geometry", Geometry("MultiPolygon"), nullable=False),
        sa.Column("centroid", Geometry("Point"), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "municipality_key IS NULL OR (country_code='DE' AND municipality_key ~ '^[0-9]{8}$')",
            name="research_area_municipality_key",
        ),
        sa.CheckConstraint(
            "(population_count IS NULL AND population_date IS NULL AND population_source IS NULL "
            "AND population_name IS NULL AND population_file_sha256 IS NULL "
            "AND population_imported_at IS NULL) OR "
            "(municipality_key IS NOT NULL AND population_count IS NOT NULL "
            "AND population_count >= 0 AND population_date IS NOT NULL "
            "AND population_source IS NOT NULL AND population_source='bkg_vg250_ew' "
            "AND population_name IS NOT NULL AND length(population_name) BETWEEN 1 AND 120 "
            "AND population_file_sha256 IS NOT NULL AND population_file_sha256 ~ '^[0-9a-f]{64}$' "
            "AND population_imported_at IS NOT NULL)",
            name="research_area_population",
        ),
        sa.UniqueConstraint("osm_type", "osm_id", name="research_area_osm_identity"),
        sa.CheckConstraint(
            "area_type IN ('region','district','municipality')", name="research_area_type"
        ),
        sa.CheckConstraint("osm_type = 'R' AND osm_id > 0", name="research_area_identity"),
        sa.CheckConstraint("source = 'osm'", name="research_area_source"),
        sa.CheckConstraint("country_code IN ('DE','DK')", name="research_area_country"),
        sa.CheckConstraint(
            "(country_code='DE' AND region_code IN ('DE-SH','DE-HH','DE-MV','DE-NI','DE-HB')) "
            "OR (country_code='DK' AND region_code='DK-83')",
            name="research_area_region",
        ),
        sa.CheckConstraint("osm_admin_level BETWEEN 2 AND 12", name="research_area_level"),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 240 AND length(display_name) BETWEEN 1 AND 1024",
            name="research_area_names",
        ),
        sa.CheckConstraint(
            "NOT ST_IsEmpty(geometry) AND ST_IsValid(geometry) AND ST_NPoints(geometry) <= 500000",
            name="research_area_geometry_valid",
        ),
        sa.CheckConstraint(
            "NOT ST_IsEmpty(centroid) AND ST_Covers(geometry,centroid)",
            name="research_area_centroid",
        ),
        schema="admin",
    )
    op.create_index(
        "research_area_geometry_idx",
        "research_area",
        ["geometry"],
        schema="admin",
        postgresql_using="gist",
    )
    op.create_index(
        "research_area_country_type_idx",
        "research_area",
        ["country_code", "area_type"],
        schema="admin",
    )


def downgrade() -> None:
    # Only imported metadata is lost; Uranus entities are untouched.
    op.drop_table("research_area", schema="admin")
