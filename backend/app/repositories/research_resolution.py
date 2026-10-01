"""Bounded literal name resolution over public Research projections only."""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal
from unicodedata import normalize
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_database import connect_admin
from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.entity_search import escape_search
from app.repositories.research import GENRE_LABELS, parameters, research_options_sql, research_sql
from app.repositories.research_areas import ResolvedResearchArea, resolve_area
from app.repositories.vector_events import PUBLIC_EVENT
from app.schemas.research_analytics import AnalyticalQueryPlan
from app.schemas.research_execution import (
    ExecutionClarification,
    ExecutionFilters,
    ResolutionCandidate,
    ResolutionField,
    ResolvedField,
)
from app.schemas.research_planner import ResearchQueryPlan

ResolutionKind = Literal["area", "venue", "organization", "category", "event_type", "genre"]


# Canonical labels and public event eligibility shared with semantic indexing.
GENRES_SQL = f"""WITH genres AS ({GENRE_LABELS})
    SELECT g.type_id::text || ':' || g.genre_id::text id,g.name label,g.name name
    FROM genres g WHERE g.genre_id<>0
    AND EXISTS (SELECT 1 FROM uranus.event_type_link l
        JOIN uranus.event e ON e.uuid=l.event_uuid
        WHERE l.type_id=g.type_id AND l.genre_id=g.genre_id AND {PUBLIC_EVENT})
"""


EVENT_TYPES_SQL = f"""WITH types AS (
    SELECT DISTINCT ON(type_id) type_id,name FROM uranus.event_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
)
    SELECT t.type_id::text id,t.name label,t.name name FROM types t
    WHERE EXISTS (SELECT 1 FROM uranus.event_type_link l
        JOIN uranus.event e ON e.uuid=l.event_uuid
        WHERE l.type_id=t.type_id AND {PUBLIC_EVENT})
"""


def taxonomy_label(value: str) -> str:
    """Normalize typography without changing words or removing diacritics."""
    value = normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans("‐‑‒–—−", "------"))
    return " ".join(value.split())


def taxonomy_forms(value: str) -> set[str]:
    """Small German inflection vocabulary, never a source of taxonomy IDs.

    Only whole labels participate. Productive -ung/-enz plurals and a few
    explicit noun paradigms avoid general suffix stripping (e.g. Jazz -> Jaz).
    Every match still needs a canonical row from PostgreSQL.
    """
    label = taxonomy_label(value)
    forms = {label}
    for plural, singular in (("ungen", "ung"), ("enzen", "enz")):
        if label.endswith(plural):
            forms.add(label[: -len(plural)] + singular)
    for paradigm in (
        {"konzert", "konzerte", "konzerten"},
        {"workshop", "workshops"},
        {"festival", "festivals"},
        {"vortrag", "vorträge", "vorträgen"},
        {"seminar", "seminare", "seminaren"},
    ):
        if label in paradigm:
            forms.update(paradigm)
    return forms


async def taxonomy_candidates(
    connection: AsyncConnection,
    kind: Literal["event_type", "genre"],
    query: str,
    type_ids: set[str] | None,
) -> list[ResolutionCandidate]:
    base = EVENT_TYPES_SQL if kind == "event_type" else GENRES_SQL
    context = "WHERE split_part(id, ':', 1)=ANY(:type_ids)" if type_ids else ""
    # Bound the in-memory vocabulary, fail closed rather than resolve a truncated
    # set as unique. The returned clarification candidates remain capped at five.
    vocabulary_limit = 4096
    rows = list(
        (
            await connection.execute(
                text(f"""WITH choices AS ({base})
                    SELECT id,label FROM choices {context}
                    ORDER BY lower(label) COLLATE "C",id COLLATE "C" LIMIT :limit"""),
                {"type_ids": sorted(type_ids or ()), "limit": vocabulary_limit + 1},
            )
        ).mappings()
    )
    if len(rows) > vocabulary_limit:
        raise APIError(503, "research_execution_unavailable", "Taxonomy resolution unavailable.")
    exact = query.strip().casefold()
    normalized = taxonomy_label(query)
    forms = taxonomy_forms(query)
    tiers: list[list[ResolutionCandidate]] = [[], [], []]
    for row in rows:
        label = row["label"]
        if label.strip().casefold() == exact:
            tier = 0
        elif taxonomy_label(label) == normalized:
            tier = 1
        elif forms & taxonomy_forms(label):
            tier = 2
        else:
            continue
        tiers[tier].append(ResolutionCandidate(entity_type=kind, id=row["id"], label=label))
    return next((matches[:5] for matches in tiers if matches), [])


async def candidates(
    connection: AsyncConnection,
    kind: ResolutionKind,
    query: str,
    settings: Settings,
    area: ResolvedResearchArea | None = None,
    type_ids: set[str] | None = None,
) -> list[ResolutionCandidate]:
    if kind == "event_type" or kind == "genre":
        return await taxonomy_candidates(
            connection, kind, query, type_ids if kind == "genre" else None
        )
    filters = ExecutionFilters(
        entity_type="venue"
        if kind == "venue"
        else "organization"
        if kind == "organization"
        else "event",
        area_id=area.area.id if area else None,
    )
    params = parameters(filters, settings, area)
    if kind == "area":
        base = "SELECT id::text id,display_name label,name FROM admin.research_area"
    elif kind == "category":
        base = f"SELECT id::text id,name label,name FROM ({research_options_sql()}) options"
    else:
        # Reuse canonical visibility/location logic, never private contact search fields.
        base = f"SELECT entity_key::text id,name label,name FROM ({research_sql()}) public_records"
    identity = query.strip()
    if kind in {"venue", "organization"}:
        try:
            identity = str(UUID(identity))
        except ValueError:
            pass
    params.update(
        identity=identity,
        exact=query.strip(),
        prefix=escape_search(query.strip()) + "%",
        substring="%" + escape_search(query.strip()) + "%",
    )
    # Categories retain their exact-label matching; entity/area search is unchanged.
    prefix = (
        "false"
        if kind == "category"
        else "(name ILIKE :prefix ESCAPE '\\' OR label ILIKE :prefix ESCAPE '\\')"
    )
    substring = (
        "false"
        if kind == "category"
        else "(name ILIKE :substring ESCAPE '\\' OR label ILIKE :substring ESCAPE '\\')"
    )
    uuid_rank = "id=:identity" if kind in {"venue", "organization"} else "false"
    rows = (
        await connection.execute(
            text(f"""WITH choices AS ({base}), ranked AS (
        SELECT id,label,CASE WHEN {uuid_rank} THEN 0
            WHEN lower(trim(label))=lower(:exact) THEN 1
            WHEN lower(trim(name))=lower(:exact) THEN 2
            WHEN {prefix} THEN 3 WHEN {substring} THEN 4 ELSE 5 END tier
        FROM choices
    ), best AS (SELECT min(tier) tier FROM ranked)
    SELECT id,label FROM ranked WHERE tier<5 AND tier=(SELECT tier FROM best)
    ORDER BY lower(label) COLLATE "C",id COLLATE "C" LIMIT 5"""),
            params,
        )
    ).mappings()
    return [ResolutionCandidate(entity_type=kind, id=r["id"], label=r["label"]) for r in rows]


@dataclass
class Resolution:
    fields: list[ResolvedField] = field(default_factory=list)
    area: ResolvedResearchArea | None = None
    target_areas: dict[str, ResolvedResearchArea] = field(default_factory=dict)
    clarification: ExecutionClarification | None = None

    def select(
        self, field_name: ResolutionField, query: str, choices: list[ResolutionCandidate]
    ) -> ResolutionCandidate | None:
        if len(choices) != 1:
            self.clarification = ExecutionClarification(
                reason="ambiguous" if choices else "no_match",
                field=field_name,
                query=query,
                candidates=choices,
            )
            return None
        target = choices[0]
        self.fields.append(ResolvedField(field=field_name, query=query, target=target))
        return target


async def resolve_plan(
    request: Request, settings: Settings, plan: ResearchQueryPlan | AnalyticalQueryPlan
) -> Resolution:
    resolved = Resolution()
    areas: list[tuple[ResolutionField, str]] = []
    if plan.area_query:
        areas.append(("area_query", plan.area_query))
    areas.extend(
        ("comparison_targets", t.query) for t in plan.comparison_targets if t.kind == "area"
    )
    if areas:
        async with connect_admin(request) as admin, admin.begin():
            await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            for field_name, query in areas:
                target = resolved.select(
                    field_name, query, await candidates(admin, "area", query, settings)
                )
                if target is None:
                    return resolved
                area = await resolve_area(admin, UUID(target.id))
                if field_name == "area_query":
                    resolved.area = area
                else:
                    resolved.target_areas[target.id] = area
    slots: list[tuple[ResolutionField, ResolutionKind, str]] = []
    if plan.venue_query:
        slots.append(("venue_query", "venue", plan.venue_query))
    if plan.organization_query:
        slots.append(("organization_query", "organization", plan.organization_query))
    slots.extend(("event_type_queries", "event_type", q) for q in plan.event_type_queries)
    slots.extend(("genre_queries", "genre", q) for q in plan.genre_queries)
    slots.extend(("category_queries", "category", q) for q in plan.category_queries)
    slots.extend(
        ("comparison_targets", t.kind, t.query) for t in plan.comparison_targets if t.kind != "area"
    )
    candidate_area = None if getattr(plan, "area_relation", "inside") == "outside" else resolved.area
    if slots:
        async with asynccontextmanager(get_connection)(request) as connection:
            for field_name, kind, query in slots:
                type_ids = {r.target.id for r in resolved.fields if r.field == "event_type_queries"}
                if kind == "genre" and type_ids:
                    choices = await candidates(
                        connection, kind, query, settings, candidate_area, type_ids
                    )
                    # A global fallback diagnoses a contradictory parent; the
                    # conflict check below prevents it from reaching execution.
                    if not choices:
                        choices = await candidates(connection, kind, query, settings)
                else:
                    choices = await candidates(connection, kind, query, settings, candidate_area)
                if resolved.select(field_name, query, choices) is None:
                    return resolved
    # Every requested genre must belong to one of the explicitly selected types.
    # Keep composite genre identities intact; never discard a contradictory filter.
    type_ids = {r.target.id for r in resolved.fields if r.field == "event_type_queries"}
    for item in resolved.fields:
        if (
            item.field == "genre_queries"
            and type_ids
            and item.target.id.split(":", 1)[0] not in type_ids
        ):
            resolved.clarification = ExecutionClarification(
                reason="taxonomy_conflict",
                field="genre_queries",
                query=item.query,
                candidates=[item.target],
            )
            return resolved
    targets = [r.target for r in resolved.fields if r.field == "comparison_targets"]
    if len({(t.entity_type, t.id) for t in targets}) != len(targets):
        resolved.clarification = ExecutionClarification(
            reason="duplicate_target", field="comparison_targets", candidates=targets
        )
    return resolved
