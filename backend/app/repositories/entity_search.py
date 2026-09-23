"""Canonical fields, presentation and ranking for entity, global and graph search."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.created_period import created_period_filter
from app.repositories.query import ReadQuery
from app.repositories.spatial import spatial_predicate
from app.repositories.temporal import temporal_predicate
from app.repositories.user_presentation import USER_DISPLAY_LABEL_SQL
from app.schemas.action import Action
from app.schemas.entities import EntitySearchFilters, EntitySearchItem, EntitySearchResponse
from app.schemas.search import (
    GlobalSearchFilters,
    GlobalSearchGroup,
    GlobalSearchItem,
    GlobalSearchResponse,
)


def escape_search(value: str) -> str:
    """Treat PostgreSQL LIKE metacharacters as literal user input."""
    return value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class SearchDefinition:
    source: str
    fields: tuple[str, ...]  # First field is always the UUID cast to text.
    label: str
    subtitle: str
    field_names: tuple[str, ...] = field(kw_only=True)
    created_at: str = field(kw_only=True)
    organization: str = "NULL::uuid"
    status: str = "NULL::text"

    def projection(self) -> str:
        fields = ",".join(f"{field} search_{i}" for i, field in enumerate(self.fields))
        return (
            f"SELECT {self.fields[0]} entity_key,{self.label} label,{self.subtitle} subtitle,"
            f"{self.created_at} created_at,{self.organization} organization_id,"
            f"{self.status} status,{fields} FROM {self.source}"
        )

    def rank(self) -> str:
        return (
            f"CASE WHEN search_0 ILIKE :exact THEN 0 "
            f"WHEN {self.matches('exact')} THEN 1 "
            f"WHEN {self.matches('prefix')} THEN 2 ELSE 3 END"
        )

    def matched_fields(self) -> str:
        fields = ",".join(
            f"CASE WHEN search_{i} ILIKE :q THEN '{name}' END"
            for i, name in enumerate(self.field_names)
        )
        return f"array_remove(ARRAY[{fields}],NULL)"

    def matches(self, parameter: str = "q") -> str:
        return " OR ".join(f"search_{i} ILIKE :{parameter}" for i in range(len(self.fields)))


# Only code-owned SQL identifiers/expressions; never derive them from request values.
SEARCH_DEFINITIONS = {
    "user": SearchDefinition(
        'uranus."user" u',
        ("u.uuid::text", "u.username", "u.display_name", "u.email", "u.first_name", "u.last_name"),
        USER_DISPLAY_LABEL_SQL,
        # Omit identity fields already used as the primary label.
        f"NULLIF(concat_ws(' · ',"
        f"NULLIF('@'||NULLIF(NULLIF(u.username,''),{USER_DISPLAY_LABEL_SQL}),"
        f"{USER_DISPLAY_LABEL_SQL}),"
        f"NULLIF(NULLIF(u.email,''),{USER_DISPLAY_LABEL_SQL})), '')",
        field_names=("uuid", "username", "display_name", "email", "first_name", "last_name"),
        created_at="u.created_at",
        status="CASE WHEN u.is_active THEN 'active' ELSE 'inactive' END",
    ),
    "organization": SearchDefinition(
        "uranus.organization o",
        ("o.uuid::text", "o.name", "o.contact_email", "o.city", "o.postal_code"),
        "o.name",
        "COALESCE(NULLIF(concat_ws(' · ',NULLIF(o.city,''),NULLIF(o.postal_code,'')),''),"
        "NULLIF(o.contact_email,''))",
        "o.uuid",
        field_names=("uuid", "name", "contact_email", "city", "postal_code"),
        created_at="o.created_at",
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
        field_names=(
            "uuid",
            "name",
            "contact_email",
            "street",
            "house_number",
            "postal_code",
            "city",
        ),
        created_at="v.created_at",
    ),
    "space": SearchDefinition(
        "uranus.space s LEFT JOIN uranus.venue v ON v.uuid=s.venue_uuid",
        ("s.uuid::text", "s.name", "v.name", "s.space_type"),
        "s.name",
        "COALESCE(NULLIF(v.name,''),NULLIF(s.space_type,''))",
        "v.org_uuid",
        field_names=("uuid", "name", "venue_name", "space_type"),
        created_at="s.created_at",
    ),
    "event": SearchDefinition(
        "uranus.event e LEFT JOIN uranus.organization o ON o.uuid=e.org_uuid",
        ("e.uuid::text", "e.title", "e.subtitle", "e.external_id"),
        "e.title",
        "COALESCE(NULLIF(e.subtitle,''),NULLIF(o.name,''),e.release_status::text,e.external_id)",
        "e.org_uuid",
        "e.release_status::text",
        field_names=("uuid", "title", "subtitle", "external_id"),
        created_at="e.created_at",
    ),
    "image": SearchDefinition(
        "uranus.pluto_image i",
        ("i.uuid::text", "i.file_name", "i.alt_text", "i.creator_name", "i.mime_type"),
        "COALESCE(NULLIF(i.alt_text,''),NULLIF(i.file_name,''),i.uuid::text)",
        "NULLIF(i.mime_type,'')",
        field_names=("uuid", "file_name", "alt_text", "creator_name", "mime_type"),
        created_at="i.created_at",
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


def entity_search_query(
    filters: EntitySearchFilters,
    settings: Settings,
    now: datetime,
    geo_scope_wkb: bytes | None = None,
) -> ReadQuery:
    spatial = (
        spatial_predicate(filters.entity_type, filters.temporal)
        if geo_scope_wkb is not None
        else "TRUE"
    )
    temporal = (
        "TRUE"
        if geo_scope_wkb is not None and filters.entity_type == "event"
        else temporal_predicate(filters.entity_type, filters.temporal)
    )
    period_sql, period_params = created_period_filter(filters.period, settings, now)
    definition = SEARCH_DEFINITIONS[filters.entity_type]
    query = escape_search(filters.q)
    return ReadQuery(
        text(f"""SELECT entity_key,label,subtitle,status FROM ({definition.projection()}) a
        WHERE ({definition.matches()}) AND {ORGANIZATION_FILTER}
        AND (CAST(:status AS text) IS NULL OR status=:status)
        AND {temporal} AND {period_sql} AND {spatial}
        ORDER BY {definition.rank()},
                 lower(label) COLLATE "C",entity_key COLLATE "C"
        LIMIT :limit"""),
        {
            **period_params,
            "geo_scope_wkb": geo_scope_wkb,
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


async def entity_search(
    connection: AsyncConnection,
    filters: EntitySearchFilters,
    settings: Settings,
    now: datetime,
    geo_scope_wkb: bytes | None = None,
) -> EntitySearchResponse:
    query = entity_search_query(filters, settings, now, geo_scope_wkb)
    result = await connection.execute(query.statement, query.parameters)
    rows = result.mappings()
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


def search_parameters(q: str) -> dict[str, str]:
    escaped = escape_search(q)
    return {"q": f"%{escaped}%", "exact": escaped, "prefix": f"{escaped}%"}


def global_search_query(filters: GlobalSearchFilters) -> ReadQuery:
    # Each branch sorts/limits in PostgreSQL before UNION; at most 60 compact rows.
    branches = []
    for kind in filters.selected_types:
        definition = SEARCH_DEFINITIONS[kind]
        branches.append(f"""(SELECT '{kind}' entity_type,entity_key,label,subtitle,
            {definition.matched_fields()} matched_fields,{definition.rank()} rank
            FROM ({definition.projection()}) a WHERE ({definition.matches()})
            ORDER BY rank,lower(label) COLLATE "C",entity_key COLLATE "C"
            LIMIT :limit)""")
    return ReadQuery(
        text(
            "SELECT entity_type,entity_key,label,subtitle,matched_fields FROM ("
            + " UNION ALL ".join(branches)
            + ') a ORDER BY entity_type COLLATE "C",rank,lower(label) COLLATE "C",'
            'entity_key COLLATE "C"'
        ),
        {**search_parameters(filters.q), "limit": filters.limit_per_type},
    )


async def global_search(
    connection: AsyncConnection, filters: GlobalSearchFilters
) -> GlobalSearchResponse:
    query = global_search_query(filters)
    rows = (await connection.execute(query.statement, query.parameters)).mappings()
    groups: dict[str, list[GlobalSearchItem]] = {}
    for row in rows:
        item = GlobalSearchItem(
            **row,
            action=Action(
                route="activity", entity_type=row["entity_type"], entity_key=row["entity_key"]
            ),
        )
        groups.setdefault(item.entity_type, []).append(item)
    return GlobalSearchResponse(
        query=filters.q,
        groups=[
            GlobalSearchGroup(entity_type=kind, items=groups[kind])
            for kind in filters.selected_types
            if kind in groups
        ],
    )
