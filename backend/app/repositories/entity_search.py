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
    fields: tuple[str, ...]  # UUID fields are identified by field_names, including related UUIDs.
    label: str
    subtitle: str
    field_names: tuple[str, ...] = field(kw_only=True)
    created_at: str = field(kw_only=True)
    organization: str = "NULL::uuid"
    status: str = "NULL::text"
    entity_key: str | None = field(default=None, kw_only=True)
    # Only event dates need a distinct, joined parent target; never a database href.
    action_key: str = field(default="NULL::text", kw_only=True)
    venue_scope: str = field(default="NULL::text", kw_only=True)

    def projection(self) -> str:
        fields = ",".join(f"{field} search_{i}" for i, field in enumerate(self.fields))
        return (
            f"SELECT {self.entity_key or self.fields[0]} entity_key,"
            f"{self.label} label,{self.subtitle} subtitle,{self.action_key} action_key,"
            f"{self.created_at} created_at,{self.organization} organization_id,"
            f"{self.status} status,{self.venue_scope} venue_scope,{fields} FROM {self.source}"
        )

    def rank(self) -> str:
        uuid_matches = " OR ".join(
            f"search_{i} ILIKE :exact" for i, name in enumerate(self.field_names) if name == "uuid"
        )
        return (
            f"CASE WHEN {uuid_matches} THEN 0 "
            f"WHEN {self.matches('exact')} THEN 1 "
            f"WHEN {self.matches('prefix')} THEN 2 ELSE 3 END"
        )

    def matched_fields(self) -> str:
        fields = ",".join(
            "CASE WHEN "
            + " OR ".join(
                f"search_{i} ILIKE :q"
                for i, field_name in enumerate(self.field_names)
                if field_name == name
            )
            + f" THEN '{name}' END"
            for name in dict.fromkeys(self.field_names)
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
        venue_scope="v.scope",
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
    "event_date": SearchDefinition(
        "uranus.event_date d LEFT JOIN uranus.event e ON e.uuid=d.event_uuid",
        (
            "d.uuid::text",
            "d.event_uuid::text",
            "e.title",
            "to_char(d.start_date,'YYYY-MM-DD')",
            "to_char(d.start_date,'DD.MM.YYYY')",
            "to_char(d.start_time,'HH24:MI')",
        ),
        "COALESCE(NULLIF(btrim(e.title),''),'Termin ohne Veranstaltungstitel')",
        "concat_ws(' · ',to_char(d.start_date,'DD.MM.YYYY'),"
        "CASE WHEN d.all_day THEN 'Ganztägig' ELSE to_char(d.start_time,'HH24:MI') END)",
        field_names=("uuid", "uuid", "title", "start_date", "start_date", "start_time"),
        created_at="d.created_at",
        organization="e.org_uuid",
        action_key="e.uuid::text",
    ),
    "partner_request": SearchDefinition(
        "uranus.organization_partner_request p "
        "LEFT JOIN uranus.organization f ON f.uuid=p.from_org_uuid "
        "LEFT JOIN uranus.organization t ON t.uuid=p.to_org_uuid",
        ("p.from_org_uuid::text", "p.to_org_uuid::text", "f.name", "t.name"),
        "COALESCE(NULLIF(btrim(f.name),''),'Organisation ohne Namen')||' → '||"
        "COALESCE(NULLIF(btrim(t.name),''),'Organisation ohne Namen')",
        "CASE p.status WHEN 'pending' THEN 'Ausstehend' "
        "WHEN 'accepted' THEN 'Angenommen' ELSE NULLIF(p.status,'') END",
        field_names=("uuid", "uuid", "name", "name"),
        created_at="p.created_at",
        organization="p.from_org_uuid",
        status="p.status",
        entity_key="'partner-request:'||p.from_org_uuid||':'||p.to_org_uuid",
    ),
    "team_membership": SearchDefinition(
        "uranus.organization_member_link m "
        "LEFT JOIN uranus.organization o ON o.uuid=m.org_uuid "
        'LEFT JOIN uranus."user" u ON u.uuid=m.user_uuid',
        (
            "m.org_uuid::text",
            "m.user_uuid::text",
            "o.name",
            "u.username",
            "u.display_name",
            "u.email",
        ),
        f"COALESCE({USER_DISPLAY_LABEL_SQL},m.user_uuid::text)",
        "COALESCE(NULLIF(btrim(o.name),''),'Organisation ohne Namen')||' · '||"
        "CASE WHEN m.has_joined THEN 'Beigetreten' ELSE 'Eingeladen' END",
        field_names=("uuid", "uuid", "name", "username", "display_name", "email"),
        created_at="m.created_at",
        organization="m.org_uuid",
        status="CASE WHEN m.has_joined THEN 'joined' ELSE 'invited' END",
        entity_key="'membership:'||m.org_uuid||':'||m.user_uuid",
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
        text(f"""SELECT entity_key,label,subtitle,status,venue_scope
        FROM ({definition.projection()}) a
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
    # Each branch sorts/limits in PostgreSQL before UNION; at most 90 compact rows.
    branches = []
    for kind in filters.selected_types:
        definition = SEARCH_DEFINITIONS[kind]
        branches.append(f"""(SELECT '{kind}' entity_type,entity_key,label,subtitle,
            action_key,venue_scope,
            {definition.matched_fields()} matched_fields,{definition.rank()} rank
            FROM ({definition.projection()}) a WHERE ({definition.matches()})
            ORDER BY rank,lower(label) COLLATE "C",entity_key COLLATE "C"
            LIMIT :limit)""")
    return ReadQuery(
        text(
            "SELECT entity_type,entity_key,label,subtitle,action_key,venue_scope,matched_fields "
            "FROM ("
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
        data = dict(row)
        parent_key = data.pop("action_key")
        kind = data["entity_type"]
        if kind == "event_date" and parent_key is not None:
            action = Action(route="activity", entity_type="event", entity_key=parent_key)
        elif kind == "partner_request":
            action = Action(
                route="partner_requests", entity_type=kind, entity_key=data["entity_key"]
            )
        elif kind == "team_membership":
            action = Action(
                route="team_invitations", entity_type=kind, entity_key=data["entity_key"]
            )
        else:
            action = Action(route="activity", entity_type=kind, entity_key=data["entity_key"])
        item = GlobalSearchItem(**data, action=action)
        groups.setdefault(item.entity_type, []).append(item)
    return GlobalSearchResponse(
        query=filters.q,
        groups=[
            GlobalSearchGroup(entity_type=kind, items=groups[kind])
            for kind in filters.selected_types
            if kind in groups
        ],
    )
