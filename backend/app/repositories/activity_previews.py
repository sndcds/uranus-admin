"""Bounded page enrichment; public routes verified against Kulturbytes client and Pluto."""

import math
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.location import EFFECTIVE_SPACE_SQL, EFFECTIVE_VENUE_SQL

# Only page identities enter this query. Lateral lookups use source keys and LIMIT,
# not one application/database round trip per item. User email is explicitly admin-only;
# credentials, activation tokens and other private fields are never selected.
PREVIEW_SQL = f"""
WITH requested AS (
 SELECT kind,key,CASE WHEN kind NOT IN ('partner_request','team_membership')
                     THEN key::uuid END id,
        CASE WHEN kind='team_membership' THEN split_part(key,':',2)::uuid END member_org,
        CASE WHEN kind='team_membership' THEN split_part(key,':',3)::uuid END member_user
 FROM unnest(CAST(:types AS text[]), CAST(:keys AS text[])) AS r(kind, key)
), image_contexts AS (
 SELECT l.pluto_image_uuid,
        CASE WHEN COUNT(DISTINCT (l.context,l.context_uuid))=1
             THEN MIN(COALESCE(o.name,v.name,e.title)) END name
 FROM requested r JOIN uranus.pluto_image_link l ON r.kind='image' AND l.pluto_image_uuid=r.id
 LEFT JOIN uranus.organization o ON l.context='organization' AND o.uuid=l.context_uuid
 LEFT JOIN uranus.venue v ON l.context='venue' AND v.uuid=l.context_uuid
 LEFT JOIN uranus.event e ON l.context='event' AND e.uuid=l.context_uuid
 GROUP BY l.pluto_image_uuid
), details AS (
 SELECT r.kind, r.key, o.city subtitle,
        NULLIF(concat_ws(', ',
          NULLIF(concat_ws(' ',NULLIF(btrim(o.street),''),NULLIF(btrim(o.house_number),'')),''),
          NULLIF(btrim(o.address_addition),''),
          NULLIF(concat_ws(' ',NULLIF(btrim(o.postal_code),''),NULLIF(btrim(o.city),'')),''),
          NULLIF(btrim(o.country),'')),'') address,
        NULL::text venue_slug, NULL::uuid event_id, NULL::uuid date_id,
        NULL::date start_date, NULL::time start_time, NULL::boolean all_day,
        NULL::text venue_name, NULL::text space_name, NULL::text event_status,
        NULL::text date_status, 'organization'::text image_context, o.uuid image_target,
        NULL::uuid direct_image
 FROM requested r JOIN uranus.organization o ON r.kind='organization' AND o.uuid=r.id
 UNION ALL
 SELECT r.kind,r.key,NULL,
        NULLIF(concat_ws(', ',
          NULLIF(concat_ws(' ',NULLIF(v.street,''),NULLIF(v.house_number,'')),''),
          NULLIF(concat_ws(' ',NULLIF(v.postal_code,''),NULLIF(v.city,'')),'')),''),
        v.slug,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'venue',v.uuid,NULL
 FROM requested r JOIN uranus.venue v ON r.kind='venue' AND v.uuid=r.id
 UNION ALL
 SELECT r.kind,r.key,v.name,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL
 FROM requested r JOIN uranus.space s ON r.kind='space' AND s.uuid=r.id
 LEFT JOIN uranus.venue v ON v.uuid=s.venue_uuid
 UNION ALL
 SELECT r.kind,r.key,e.subtitle,NULL,NULL,e.uuid,d.uuid,d.start_date,d.start_time,d.all_day,
        NULL,NULL,e.release_status::text,
        COALESCE(NULLIF(d.release_status::text,'inherited'),e.release_status::text),
        'event',e.uuid,NULL
 FROM requested r JOIN uranus.event e ON r.kind='event' AND e.uuid=r.id
 LEFT JOIN LATERAL (
   -- Admin previews include unpublished dates; public_url checks both statuses separately.
   SELECT d.uuid,d.start_date,d.start_time,d.all_day,d.release_status
   FROM uranus.event_date d WHERE d.event_uuid=e.uuid
     AND (d.start_date > CAST(:today AS date) OR (d.start_date=CAST(:today AS date)
       AND (d.all_day IS TRUE OR d.start_time IS NULL OR d.start_time >= CAST(:clock AS time))))
   ORDER BY d.start_date,d.start_time NULLS LAST,d.uuid LIMIT 1
 ) d ON TRUE
 UNION ALL
 SELECT r.kind,r.key,NULL,NULL,NULL,e.uuid,d.uuid,d.start_date,d.start_time,d.all_day,
        v.name,s.name,e.release_status::text,
        COALESCE(NULLIF(d.release_status::text,'inherited'),e.release_status::text),
        'event',e.uuid,NULL
 FROM requested r JOIN uranus.event_date d ON r.kind='event_date' AND d.uuid=r.id
 LEFT JOIN uranus.event e ON e.uuid=d.event_uuid
 LEFT JOIN uranus.venue v ON v.uuid={EFFECTIVE_VENUE_SQL}
 LEFT JOIN uranus.space s ON s.uuid={EFFECTIVE_SPACE_SQL}
 UNION ALL
 SELECT r.kind,r.key,
        CASE WHEN m.invited_at IS NOT NULL THEN 'Eingeladen: ' ||
          to_char(m.invited_at AT TIME ZONE :source_tz AT TIME ZONE :admin_tz,'DD.MM.YYYY HH24:MI')
          || ' (' || :admin_tz || ')' END,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL
 FROM requested r JOIN uranus.organization_member_link m
 ON r.kind='team_membership' AND m.org_uuid=r.member_org AND m.user_uuid=r.member_user
 UNION ALL
 SELECT r.kind,r.key,linked.name,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
        NULL,NULL,i.uuid
 FROM requested r JOIN uranus.pluto_image i ON r.kind='image' AND i.uuid=r.id
 LEFT JOIN image_contexts linked ON linked.pluto_image_uuid=i.uuid
 UNION ALL
 SELECT r.kind,r.key,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL
 FROM requested r JOIN uranus."user" u ON r.kind='user' AND u.uuid=r.id
)
SELECT d.*, COALESCE(d.direct_image,img.uuid) image_uuid,
       NULLIF(btrim(u.email),'') email,
       public.ST_Y(o.point) latitude, public.ST_X(o.point) longitude
FROM details d
LEFT JOIN uranus."user" u ON d.kind='user' AND u.uuid=CASE WHEN d.kind='user' THEN d.key::uuid END
LEFT JOIN uranus.organization o ON d.kind='organization'
 AND o.uuid=CASE WHEN d.kind='organization' THEN d.key::uuid END
LEFT JOIN LATERAL (
 SELECT i.uuid FROM uranus.pluto_image_link l
 JOIN uranus.pluto_image i ON i.uuid=l.pluto_image_uuid
 WHERE l.context=d.image_context AND l.context_uuid=d.image_target
   AND ((l.context='organization' AND l.identifier='main_logo')
     OR (l.context='venue' AND l.identifier IN ('main_photo','main_logo'))
     OR (l.context='event' AND l.identifier='main'))
 ORDER BY CASE WHEN l.identifier='main_photo' THEN 0 ELSE 1 END,l.identifier,i.uuid LIMIT 1
) img ON TRUE
"""
PUBLIC_STATUSES = {"released", "cancelled", "deferred", "rescheduled"}
PUBLIC_SITE = "https://kulturbytes.de"
PUBLIC_API = "https://api.kulturbytes.de"


def image_url(image_uuid: UUID | str | None, api_url: str) -> str | None:
    """Public Pluto thumbnail; never expose private origins or stored URL strings."""
    if image_uuid is None or api_url.rstrip("/") != PUBLIC_API:
        return None
    try:
        identifier = UUID(str(image_uuid))
    except ValueError:
        return None
    query = urlencode({"width": 320})
    return f"{PUBLIC_API}/api/image/{identifier}?{query}"


def avatar_url(user_uuid: str | UUID | None, api_url: str) -> str | None:
    """Public Uranus avatar candidate; a missing file returns 404 and the UI falls back."""
    if user_uuid is None or api_url.rstrip("/") != PUBLIC_API:
        return None
    try:
        identifier = UUID(str(user_uuid))
    except ValueError:
        return None
    return f"{PUBLIC_API}/api/user/{identifier}/avatar/128"


def location(latitude: float | None, longitude: float | None) -> dict[str, float] | None:
    if (
        latitude is None
        or longitude is None
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    return {"latitude": latitude, "longitude": longitude}


def public_url(row: dict[str, Any]) -> str | None:
    if row["kind"] == "venue":
        slug = row["venue_slug"]
        if slug and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            return f"{PUBLIC_SITE}/de/ort/{slug}"
        if UUID(row["key"]).version == 7:
            return f"{PUBLIC_SITE}/de/ort/{row['key']}"
    if (
        row["kind"] in {"event", "event_date"}
        and row["event_status"] in PUBLIC_STATUSES
        and row["date_status"] in PUBLIC_STATUSES
        and row["date_id"] is not None
        and row["date_id"].version == 7
    ):
        return f"{PUBLIC_SITE}/de/veranstaltung/{row['event_id']}/{row['date_id']}"
    return None


async def activity_previews(
    connection: AsyncConnection, settings: Settings, items: list[dict[str, Any]], now: datetime
) -> dict[tuple[str, str], dict[str, Any]]:
    if not items:
        return {}
    local = now.astimezone(ZoneInfo(settings.event_timezone))
    rows = (
        await connection.execute(
            text(PREVIEW_SQL),
            {
                "types": [item["entity_type"] for item in items],
                "keys": [item["entity_key"] for item in items],
                "today": local.date(),
                "source_tz": settings.uranus_timestamp_timezone,
                "admin_tz": settings.admin_timezone,
                "clock": local.time().replace(tzinfo=None),
            },
        )
    ).mappings()
    previews = {}
    # A local/unrelated snapshot must not silently link to records on the public instance.
    public_instance = settings.uranus_api_url.rstrip("/") == PUBLIC_API
    for mapping in rows:
        row = dict(mapping)
        parts = [row["subtitle"]]
        if row["start_date"] is not None:
            time = (
                "ganztägig"
                if row["all_day"]
                else row["start_time"].strftime("%H:%M")
                if row["start_time"]
                else "Uhrzeit unbekannt"
            )
            prefix = "Termin"
            if row["kind"] == "event":
                prefix = (
                    "Nächster öffentlicher Termin"
                    if row["event_status"] in PUBLIC_STATUSES
                    and row["date_status"] in PUBLIC_STATUSES
                    else "Nächster Termin"
                )
            parts.append(
                f"{prefix}: {row['start_date']:%d.%m.%Y} · {time} ({settings.event_timezone})"
            )
        parts.extend([row["venue_name"], row["space_name"]])
        previews[(row["kind"], row["key"])] = {
            "subtitle": " · ".join(part for part in parts if part) or None,
            "address": row["address"],
            "image_url": (
                avatar_url(row["key"], settings.uranus_api_url)
                if row["kind"] == "user"
                else image_url(row["image_uuid"], settings.uranus_api_url)
            ),
            "email": row["email"],
            "location": location(row["latitude"], row["longitude"]),
            "public_url": public_url(row) if public_instance else None,
        }
    return previews
