"""Extend research regions to all Germany and Denmark, retaining all area data."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Frozen constraints; never import mutable application definitions.
PREVIOUS_REGIONS = (
    "(country_code='DE' AND region_code IN ('DE-SH','DE-HH','DE-MV','DE-NI','DE-HB')) "
    "OR (country_code='DK' AND region_code='DK-83')"
)
ALL_REGIONS = (
    "(country_code='DE' AND region_code IN ('DE-SH','DE-HH','DE-MV','DE-NI','DE-HB',"
    "'DE-BB','DE-BE','DE-BW','DE-BY','DE-HE','DE-NW',"
    "'DE-RP','DE-SL','DE-SN','DE-ST','DE-TH')) "
    "OR (country_code='DK' AND region_code IN ('DK-81','DK-82','DK-83','DK-84','DK-85'))"
)


def upgrade() -> None:
    op.drop_constraint("research_area_region", "research_area", schema="admin", type_="check")
    op.create_check_constraint("research_area_region", "research_area", ALL_REGIONS, schema="admin")


def downgrade() -> None:
    # Serialize the guard with concurrent imports. Fail without deleting or changing
    # data if the old scope cannot represent the stored inventory. Also works offline.
    op.execute("LOCK TABLE admin.research_area IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM admin.research_area WHERE NOT ("
        + PREVIOUS_REGIONS
        + ")) THEN RAISE EXCEPTION 'Cannot downgrade research regions: "
        "areas outside the previous scope still exist'; END IF; END $$"
    )
    op.drop_constraint("research_area_region", "research_area", schema="admin", type_="check")
    op.create_check_constraint(
        "research_area_region", "research_area", PREVIOUS_REGIONS, schema="admin"
    )
