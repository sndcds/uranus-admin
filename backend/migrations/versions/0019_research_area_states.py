"""Allow explicitly reviewed state boundaries; no backfill or reclassification."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("research_area_type", "research_area", schema="admin", type_="check")
    op.create_check_constraint(
        "research_area_type",
        "research_area",
        "area_type IN ('region','district','municipality','state')",
        schema="admin",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE admin.research_area IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM admin.research_area WHERE area_type='state') THEN
            RAISE EXCEPTION 'Cannot downgrade research areas while state rows exist';
        END IF;
    END $$""")
    op.drop_constraint("research_area_type", "research_area", schema="admin", type_="check")
    op.create_check_constraint(
        "research_area_type",
        "research_area",
        "area_type IN ('region','district','municipality')",
        schema="admin",
    )
