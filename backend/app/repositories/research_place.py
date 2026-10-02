"""Place selection over effective venue data. All SQL identifiers are application-owned."""

from app.schemas.research_location import Place, PlaceFilter


def place_filter(place: Place) -> PlaceFilter | None:
    address = place.address
    if (
        address
        and address.road
        and address.city
        and (place.place_type in {"street", "road"} or address.house_number)
    ):
        return PlaceFilter(
            mode="address", road=address.road, city=address.city, house_number=address.house_number
        )
    if (
        place.bbox
        and place.osm_type != "node"
        and place.bbox[0] < place.bbox[2]
        and place.bbox[1] < place.bbox[3]
    ):
        return PlaceFilter(mode="bbox", bbox=place.bbox)
    if place.latitude is not None and place.longitude is not None:
        return PlaceFilter(mode="radius", latitude=place.latitude, longitude=place.longitude)
    return None


# Structured addresses do not require a point. Geometry branches fail closed for
# missing/invalid points. CASE prevents casting invalid coordinates to geography.
PLACE_PREDICATE = r"""CASE :place_mode
    WHEN 'none' THEN TRUE
    WHEN 'address' THEN
        lower(regexp_replace(trim(v.street), '\s+', ' ', 'g')) =
            lower(regexp_replace(trim(CAST(:place_road AS text)), '\s+', ' ', 'g'))
        AND lower(regexp_replace(trim(v.city), '\s+', ' ', 'g')) =
            lower(regexp_replace(trim(CAST(:place_city AS text)), '\s+', ' ', 'g'))
        AND (CAST(:place_house AS text) IS NULL OR
             lower(trim(v.house_number)) = lower(trim(CAST(:place_house AS text))))
    ELSE CASE WHEN v.point IS NOT NULL AND ST_IsValid(v.point) AND NOT ST_IsEmpty(v.point)
        AND ST_SRID(v.point)=4326
        AND ST_X(v.point) BETWEEN -180 AND 180 AND ST_Y(v.point) BETWEEN -90 AND 90
    THEN CASE :place_mode
        WHEN 'bbox' THEN v.point &&
            ST_MakeEnvelope(:place_west,:place_south,:place_east,:place_north,4326)
            AND ST_Covers(
                ST_MakeEnvelope(:place_west,:place_south,:place_east,:place_north,4326),v.point)
        WHEN 'radius' THEN ST_DWithin(v.point::geography,
            ST_SetSRID(ST_MakePoint(:place_longitude,:place_latitude),4326)::geography,:place_radius)
        ELSE FALSE END
    ELSE FALSE END END"""


def place_parameters(selection: PlaceFilter | None) -> dict[str, object]:
    bbox = selection.bbox if selection and selection.bbox else (None, None, None, None)
    return {
        "place_mode": selection.mode if selection else "none",
        "place_road": selection.road if selection else None,
        "place_city": selection.city if selection else None,
        "place_house": selection.house_number if selection else None,
        "place_latitude": selection.latitude if selection else None,
        "place_longitude": selection.longitude if selection else None,
        "place_south": bbox[0],
        "place_west": bbox[1],
        "place_north": bbox[2],
        "place_east": bbox[3],
        "place_radius": selection.radius_m if selection else 250,
    }
