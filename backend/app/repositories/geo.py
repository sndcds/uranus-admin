"""Admin cache import, including polygon repair within PostGIS."""

import json
import logging
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.errors import APIError
from app.schemas.geo import GeoArea, GeoAreaImport
from app.services.geo.scopes import AREA_COLUMNS, resolve_geo_scope
from app.services.nominatim import NominatimClient

logger = logging.getLogger("admin.geo")


async def import_area(
    admin: AsyncConnection, identity: GeoAreaImport, provider: NominatimClient
) -> GeoArea:
    params = identity.model_dump()
    existing = (
        await admin.execute(
            text(
                "SELECT id FROM admin.geo_area WHERE source=:source "
                "AND source_type=:source_type AND source_id=:source_id"
            ),
            params,
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("geo_area_cache_hit")
        return (await resolve_geo_scope(admin, existing)).area
    # End the read transaction before waiting on the provider.
    await admin.rollback()
    try:
        item, geometry = await provider.lookup_area(identity.source_id)
        params.update(
            item.model_dump(
                exclude={"provider", "osm_type", "osm_id", "eligible_for_scope", "bbox"}
            )
        )
        params.update(id=uuid4(), geometry=geometry, hierarchy=json.dumps(item.hierarchy))
        async with admin.begin():
            # MakeValid can return a collection; retain only polygonal parts.
            row = (
                (
                    await admin.execute(
                        text(f"""
                WITH normalized AS MATERIALIZED (
                  SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(
                    ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)),3)) g
                )
                INSERT INTO admin.geo_area
                  (id,source,source_type,source_id,name,display_name,country_code,admin_level,kind,
                   provider_class,provider_type,provider_addresstype,geometry,bbox,hierarchy,
                   fetched_at,created_at,updated_at)
                SELECT :id,:source,:source_type,:source_id,:name,:display_name,:country_code,
                  :admin_level,:kind,:provider_class,:provider_type,:provider_addresstype,g,
                  CASE WHEN NOT ST_IsEmpty(g) THEN ST_Envelope(g) ELSE NULL END,
                  CAST(:hierarchy AS jsonb),now(),now(),now()
                FROM normalized WHERE NOT ST_IsEmpty(g) AND ST_IsValid(g)
                ON CONFLICT (source,source_type,source_id) DO UPDATE SET source=EXCLUDED.source
                RETURNING {AREA_COLUMNS}
            """),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise APIError(
                    422, "geo_area_geometry_invalid", "Area geometry is empty after repair."
                )
        logger.info("geo_area_imported")
        return GeoArea.model_validate(row)
    except APIError:
        logger.info("geo_area_import_failed")
        raise
