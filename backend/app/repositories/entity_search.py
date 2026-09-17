"""Fixed search projections shared by autocomplete and paginated entity lists."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.temporal import temporal_predicate
from app.schemas.action import Action
from app.schemas.entities import EntitySearchFilters, EntitySearchItem, EntitySearchResponse


def escape_search(value: str) -> str:
    """Treat PostgreSQL LIKE metacharacters as literal user input."""
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class SearchDefinition:
    source: str
    fields: tuple[str, ...]  # First field is always the UUID cast to text.
    label: str
    subtitle: str
    organization: str = "NULL::uuid"
    status: str = "NULL::text"

    def projection(self) -> str:
        fields = ",".join(f"{field} search_{i}" for i, field in enumerate(self.fields))
        return (
            f"SELECT {self.fields[0]} entity_key,{self.label} label,{self.subtitle} subtitle,"
            f"{self.organization} organization_id,{self.status} status,{fields} FROM {self.source}"
        )

    def matches(self, parameter: str = "q") -> str:
        return " OR ".join(f"search_{i} ILIKE :{parameter}" for i in range(len(self.fields)))


# Only code-owned SQL identifiers/expressions; never derive them from request values.
SEARCH_DEFINITIONS = {
    "user": SearchDefinition(
        'uranus."user" u',
        ("u.uuid::text", "u.username", "u.display_name", "u.email", "u.first_name", "u.last_name"),
        "COALESCE(NULLIF(u.display_name,''),NULLIF(u.username,''),NULLIF(u.email,''),u.uuid::text)",
        "NULLIF(concat_ws(' · ', '@'||NULLIF(u.username,''),NULLIF(u.email,'')),'')",
        status="CASE WHEN u.is_active THEN 'active' ELSE 'inactive' END",
    ),
    "organization": SearchDefinition(
        "uranus.organization o",
        ("o.uuid::text", "o.name", "o.contact_email", "o.city", "o.postal_code"),
        "o.name",
        "COALESCE(NULLIF(concat_ws(' · ',NULLIF(o.city,''),NULLIF(o.postal_code,'')),''),"
        "NULLIF(o.contact_email,''))",
        "o.uuid",
    ),
    "venue": SearchDefinition(
        "uranus.venue v LEFT JOIN uranus.organization o ON o.uuid=v.org_uuid",
        (
            "v.uuid::text",
            "v.name",
            "v.contact_email",
            "v.street",
            "v.house_number",
            "v.postal_code",
            "v.city",
        ),
        "v.name",
        "COALESCE(NULLIF(concat_ws(' · ',"
        "NULLIF(concat_ws(' ',NULLIF(v.street,''),NULLIF(v.house_number,'')),''),"
        "NULLIF(concat_ws(' ',NULLIF(v.postal_code,''),NULLIF(v.city,'')),'')),''),o.name)",
        "v.org_uuid",
    ),
    "space": SearchDefinition(
        "uranus.space s LEFT JOIN uranus.venue v ON v.uuid=s.venue_uuid",
        ("s.uuid::text", "s.name", "v.name", "s.space_type"),
        "s.name",
        "COALESCE(NULLIF(v.name,''),NULLIF(s.space_type,''))",
        "v.org_uuid",
    ),
    "event": SearchDefinition(
        "uranus.event e LEFT JOIN uranus.organization o ON o.uuid=e.org_uuid",
        ("e.uuid::text", "e.title", "e.subtitle", "e.external_id"),
        "e.title",
        "COALESCE(NULLIF(e.subtitle,''),NULLIF(o.name,''),e.release_status::text,e.external_id)",
        "e.org_uuid",
        "e.release_status::text",
    ),
    "image": SearchDefinition(
        "uranus.pluto_image i",
        ("i.uuid::text", "i.file_name", "i.alt_text", "i.creator_name", "i.mime_type"),
        "COALESCE(NULLIF(i.alt_text,''),NULLIF(i.file_name,''),i.uuid::text)",
        "NULLIF(i.mime_type,'')",
    ),
}

# Shared organization semantics, including invited members and linked images.
ORGANIZATION_FILTER = """(CAST(:org AS uuid) IS NULL OR a.organization_id=:org
  OR (:kind='user' AND EXISTS (SELECT 1 FROM uranus.organization_member_link m
      WHERE m.user_uuid::text=a.entity_key AND m.org_uuid=:org))
  OR (:kind='image' AND EXISTS (SELECT 1 FROM uranus.pluto_image_link l
      LEFT JOIN uranus.venue v ON l.context='venue' AND v.uuid=l.context_uuid
      LEFT JOIN uranus.event e ON l.context='event' AND e.uuid=l.context_uuid
      WHERE l.pluto_image_uuid::text=a.entity_key AND
        ((l.context='organization' AND l.context_uuid=:org) OR v.org_uuid=:org
         OR e.org_uuid=:org))))"""


async def entity_search(
    connection: AsyncConnection, filters: EntitySearchFilters, settings: Settings, now: datetime
) -> EntitySearchResponse:
    temporal = temporal_predicate(filters.entity_type, filters.temporal)
    definition = SEARCH_DEFINITIONS[filters.entity_type]
    query = escape_search(filters.q)
    rows = (
        await connection.execute(
            text(f"""SELECT entity_key,label,subtitle,status FROM ({definition.projection()}) a
        WHERE ({definition.matches()}) AND {ORGANIZATION_FILTER}
        AND (CAST(:status AS text) IS NULL OR status=:status) AND {temporal}
        ORDER BY CASE WHEN {definition.matches("exact")} THEN 0
                      WHEN {definition.matches("prefix")} THEN 1 ELSE 2 END,
                 lower(label) COLLATE "C",entity_key COLLATE "C"
        LIMIT :limit"""),
            {
                "q": f"%{query}%",
                "exact": query,
                "prefix": f"{query}%",
                "kind": filters.entity_type,
                "org": filters.organization_id,
                "status": filters.status,
                "limit": filters.limit,
                "event_tz": settings.event_timezone,
                "temporal_now": now,
            },
        )
    ).mappings()
    return EntitySearchResponse(
        items=[
            EntitySearchItem(
                **row,
                entity_type=filters.entity_type,
                action=Action(
                    route="activity", entity_type=filters.entity_type, entity_key=row["entity_key"]
                ),
            )
            for row in rows
        ]
    )
