"""Bounded exact-first resolution; optional vectors propose source-revalidated taxonomy."""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Literal, cast
from unicodedata import normalize
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_database import connect_admin
from app.clients.research_geocoder import ResearchGeocoderClient, unavailable
from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.entity_search import escape_search
from app.repositories.research import parameters, research_options_sql, research_sql
from app.repositories.research_administrative import administrative_reference
from app.repositories.research_administrative_metadata import administrative_level_sql
from app.repositories.research_areas import ResolvedResearchArea, resolve_area
from app.repositories.research_place import place_filter
from app.repositories.research_taxonomy import EVENT_TYPES_SQL as EVENT_TYPES_SQL
from app.repositories.research_taxonomy import GENRES_SQL as GENRES_SQL
from app.research.administrative_catalog import load_inventory
from app.research.administrative_resolver import resolve_administrative_area
from app.research.capabilities import boundary_execution, require_supported_spatial
from app.research.context import ResearchExecutionContext
from app.research.geography import (
    ADMINISTRATIVE_LEVELS,
    AdministrativeHierarchy,
    AdministrativeLevel,
    NamedPlaceRef,
    ResolvedAdministrativeAreaRef,
    ResolvedAdministrativeConstraint,
    SpatialConstraint,
    UnresolvedAdministrativeAreaRef,
    administrative_constraints,
    uses_user_location,
)
from app.research.plan import InternalResearchPlan
from app.schemas.research_execution import (
    ExecutionClarification,
    ExecutionFilters,
    ResolutionCandidate,
    ResolutionField,
    ResolvedField,
)
from app.schemas.research_location import PlaceFilter
from app.services.taxonomy_resolution import outcome, resolve_taxonomy_semantic

ResolutionKind = Literal["area", "venue", "organization", "category", "event_type", "genre"]


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
    *,
    expected_level: AdministrativeLevel | None = None,
) -> list[ResolutionCandidate]:
    if kind == "event_type" or kind == "genre":
        exact = await taxonomy_candidates(
            connection, kind, query, type_ids if kind == "genre" else None
        )
        if exact:
            outcome("exact_hit" if len(exact) == 1 else "exact_ambiguous")
            return exact
        if settings.research_taxonomy_policy_path is None:
            return []
        # Planner taxonomy slots are lexical hints, not authoritative hierarchy
        # levels. Check the other level exactly before using any vectors.
        other: Literal["event_type", "genre"] = "genre" if kind == "event_type" else "event_type"
        exact = await taxonomy_candidates(connection, other, query, type_ids)
        if exact:
            outcome("exact_hit" if len(exact) == 1 else "exact_ambiguous")
            return exact
        return await resolve_taxonomy_semantic(connection, settings, query, type_ids=type_ids)
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
        if expected_level is not None:
            # Filter before ranking/LIMIT, so wrong-level rows cannot hide valid
            # matches or exhaust the five-candidate budget. No geometry N+1.
            base += f" WHERE ({administrative_level_sql()})=:expected_area_level"
            params["expected_area_level"] = expected_level
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
    place: PlaceFilter | None = None
    spatial_constraints: tuple[SpatialConstraint, ...] = ()
    administrative_hierarchy: AdministrativeHierarchy = field(
        default_factory=lambda: AdministrativeHierarchy(())
    )

    inventory: tuple[ResolvedAdministrativeAreaRef, ...] = ()
    inventory_countries: tuple[str, ...] = ()

    @property
    def area_relation(self) -> Literal["inside", "outside"]:
        constraints = administrative_constraints(self.spatial_constraints)
        if constraints and constraints[0].relation == "outside":
            return "outside"
        return "inside"

    def select(
        self, field_name: ResolutionField, query: str, choices: list[ResolutionCandidate]
    ) -> ResolutionCandidate | None:
        if len(choices) != 1:
            self.clarification = ExecutionClarification(
                reason="ambiguous" if choices else "no_match",
                field=field_name,
                query=query,
                candidates=[
                    choice.model_copy(update={"id": f"choice-{i}"})
                    if choice.entity_type in {"event_type", "genre"}
                    else choice
                    for i, choice in enumerate(choices)
                ],
            )
            return None
        target = choices[0]
        self.fields.append(ResolvedField(field=field_name, query=query, target=target))
        return target


async def resolve_plan(
    request: Request,
    settings: Settings,
    plan: InternalResearchPlan,
    context: ResearchExecutionContext,
) -> Resolution:
    require_supported_spatial(plan)
    resolved = Resolution()
    location_context = context.location_context
    query = next(
        (
            c.reference.name
            for c in plan.spatial_constraints
            if isinstance(c.reference, NamedPlaceRef)
        ),
        None,
    )
    nearby = uses_user_location(plan.spatial_constraints)
    if query or nearby:
        if nearby and location_context is None:
            resolved.clarification = ExecutionClarification(
                reason="planner", planner_state="needs_location"
            )
            return resolved
        if query or nearby:
            geocoder: ResearchGeocoderClient | None = request.app.state.research_geocoder
            if geocoder is None:
                raise unavailable()
            field_name: ResolutionField = "place_query" if query else "location_context"
            if nearby and location_context is not None and location_context.latitude is not None:
                assert location_context.longitude is not None
                # Browser labels never establish identity. Coordinates are sufficient
                # to execute nearby; reverse supplies an optional canonical label only.
                if not location_context.display_name:
                    canonical = await geocoder.reverse(
                        location_context.latitude, location_context.longitude
                    )
                    if canonical and canonical.display_name:
                        resolved.fields.append(
                            ResolvedField(
                                field="location_context",
                                query="Aktueller Standort",
                                target=ResolutionCandidate(
                                    entity_type="place",
                                    id="current-location",
                                    label=canonical.display_name,
                                    place=canonical,
                                ),
                            )
                        )
                resolved.place = PlaceFilter(
                    mode="radius",
                    latitude=location_context.latitude,
                    longitude=location_context.longitude,
                    radius_m=500,
                )
            else:
                query = query or (location_context.display_name if location_context else None)
                assert query is not None
                places = await geocoder.search(query)
                choices = [
                    ResolutionCandidate(
                        entity_type="place",
                        id=f"{p.osm_type}:{p.osm_id}"
                        if p.osm_type and p.osm_id
                        else sha256(p.model_dump_json().encode()).hexdigest(),
                        label=p.display_name or query,
                        place=p,
                    )
                    for p in places
                ]
                target = resolved.select(field_name, query, choices)
                if target is None:
                    return resolved
                assert target.place is not None
                resolved.place = place_filter(target.place)
                if resolved.place is None:
                    resolved.clarification = ExecutionClarification(
                        reason="no_match", field=field_name, query=query
                    )
                    return resolved
    areas: list[tuple[ResolutionField, UnresolvedAdministrativeAreaRef]] = []
    area_constraints = administrative_constraints(plan.spatial_constraints)
    for constraint in area_constraints:
        assert isinstance(constraint.reference, UnresolvedAdministrativeAreaRef)
        areas.append(("area_query", constraint.reference))
    areas.extend(
        ("comparison_targets", UnresolvedAdministrativeAreaRef(t.query))
        for t in plan.comparison_targets
        if t.kind == "area"
    )
    if boundary_execution(plan):
        # The boundary/inventory provider supplies geographic identity and roles.
        # Cached single-area selections retain their existing persisted authority.
        for constraint in area_constraints:
            assert isinstance(constraint.reference, UnresolvedAdministrativeAreaRef)
            geocoder = request.app.state.research_geocoder
            if geocoder is None:
                raise unavailable()
            reference = await resolve_administrative_area(geocoder, constraint.reference)
            resolved.spatial_constraints += (replace(constraint, reference=reference),)
            resolved.administrative_hierarchy = AdministrativeHierarchy(
                (*resolved.administrative_hierarchy.areas, reference)
            )
            resolved.select(
                "area_query",
                constraint.reference.name,
                [
                    ResolutionCandidate(
                        entity_type="area", id=str(reference.resolved_id), label=reference.name
                    )
                ],
            )
        if plan.group_by in ADMINISTRATIVE_LEVELS or "municipality" in plan.groupings:
            boundaries = tuple(
                ResolvedAdministrativeConstraint(
                    cast(Literal["inside", "outside"], c.relation),
                    cast(ResolvedAdministrativeAreaRef, c.reference),
                )
                for c in resolved.spatial_constraints
            )
            resolved.inventory, resolved.inventory_countries = await load_inventory(
                settings.research_administrative_catalog_path,
                cast(
                    AdministrativeLevel,
                    "municipality" if "municipality" in plan.groupings else plan.group_by,
                ),
                boundaries,
            )
    elif areas:
        async with connect_admin(request) as admin, admin.begin():
            await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            for field_name, requested in areas:
                query = requested.name
                choices = await candidates(
                    admin, "area", query, settings, expected_level=requested.expected_level
                )
                if len(choices) != 1:
                    resolved.select(field_name, query, choices)
                    return resolved
                target = choices[0]
                area = await resolve_area(admin, UUID(target.id))
                reference = administrative_reference(area)
                # Defense in depth: candidate classification is not authoritative
                # execution metadata. Recheck the loaded boundary before recording
                # a successful resolution or passing any geometry to source SQL.
                if (
                    requested.expected_level is not None
                    and reference.level != requested.expected_level
                ):
                    resolved.clarification = ExecutionClarification(
                        reason="no_match", field=field_name, query=query
                    )
                    return resolved
                resolved.select(field_name, query, choices)
                resolved.administrative_hierarchy = AdministrativeHierarchy(
                    (*resolved.administrative_hierarchy.areas, reference)
                )
                if field_name == "area_query":
                    resolved.area = area
                    resolved.spatial_constraints += (
                        replace(area_constraints[0], reference=reference),
                    )
                else:
                    resolved.target_areas[target.id] = area
    slots: list[tuple[ResolutionField, ResolutionKind, str]] = []
    if plan.filters.venue_query:
        slots.append(("venue_query", "venue", plan.filters.venue_query))
    if plan.filters.organization_query:
        slots.append(("organization_query", "organization", plan.filters.organization_query))
    slots.extend(("event_type_queries", "event_type", q) for q in plan.filters.event_type_queries)
    slots.extend(("genre_queries", "genre", q) for q in plan.filters.genre_queries)
    slots.extend(("category_queries", "category", q) for q in plan.filters.category_queries)
    slots.extend(
        ("comparison_targets", t.kind, t.query) for t in plan.comparison_targets if t.kind != "area"
    )
    candidate_area = None if resolved.area_relation == "outside" else resolved.area
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
                # A semantic proposal may resolve a Planner type term to a genre
                # (or vice versa). Preserve the canonical hierarchy in execution.
                selected_field = field_name
                if len(choices) == 1 and kind in {"event_type", "genre"}:
                    selected_field = (
                        "genre_queries"
                        if choices[0].entity_type == "genre"
                        else "event_type_queries"
                    )
                if resolved.select(selected_field, query, choices) is None:
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
