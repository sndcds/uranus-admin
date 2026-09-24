"""Explicit view registry. Pure query planning, never execute a page to discover its SQL."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel
from sqlalchemy import text

from app.admin_tables import finding, record_mark
from app.api import checks as check_api
from app.api import notifications as notification_api
from app.api.findings import suggestions_query
from app.config import Settings
from app.repositories import (
    activity,
    dashboard,
    entities,
    entity_search,
    event_content,
    geocode,
    graph,
    queues,
    statistics,
)
from app.repositories.activity_previews import preview_query
from app.repositories.geocode_sources import source_query
from app.repositories.quality_sources import SOURCE_QUERIES
from app.repositories.query import ReadQuery
from app.repositories.spatial import SPATIAL_TYPES
from app.schemas.activity import ActivityFilters
from app.schemas.entities import EntitySection
from app.schemas.finding import FindingFilters
from app.schemas.queues import QueueKind
from app.services import checks, marks
from app.services.geo.membership import membership_query
from app.services.geo.scopes import geo_scope_query
from app.services.notifications.config import capability_query, organization_config_query
from app.services.periods import period_window, previous_window
from app.services.statistics import automatic_interval, bucket_windows, statistics_window
from app.sql_diagnostics.provenance import models as m
from app.sql_diagnostics.provenance.render import RenderedQuery, projection_columns, render

COVERAGE = json.loads(Path(__file__).with_name("coverage.json").read_text())
ENTITY_COLUMNS = (
    "entity_type",
    "entity_key",
    "entity_name",
    "organization_id",
    "organization_name",
    "status",
    "venue_scope",
    "created_at",
)
PREVIEW_COLUMNS = (
    "kind",
    "key",
    "subtitle",
    "address",
    "venue_slug",
    "event_id",
    "date_id",
    "start_date",
    "start_time",
    "all_day",
    "venue_name",
    "space_name",
    "event_status",
    "date_status",
    "image_context",
    "image_target",
    "direct_image",
    "image_uuid",
    "email",
    "latitude",
    "longitude",
)


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    datasource: Literal["uranus", "admin"]
    rendered: RenderedQuery
    implementation_ref: str
    dependencies: tuple[str, ...] = ()
    description: str = "Registrierte Runtime-Abfrage. Ausführung zeigt maximal 50 Zeilen."


MODELS: dict[str, type[BaseModel]] = {
    "dashboard": m.DashboardParameters,
    "quality": m.DashboardParameters,
    "activity": m.ActivityParameters,
    "findings": m.FindingParameters,
    "checks": m.PageParameters,
    "checks.detail": m.DetailParameters,
    "geocoding": m.GeocodeParameters,
    "geocoding.detail": m.DetailParameters,
    "marks": m.MarkParameters,
    "marks.detail": m.DetailParameters,
    "graph": m.GraphParameters,
    "graph.search": m.GraphSearchParameters,
    "entity-search": m.EntitySearchParameters,
    "search": m.GlobalSearchParameters,
    "statistics": m.StatisticsParameters,
    "statistics.content": m.ContentParameters,
    "notifications": m.NotificationParameters,
    "notifications.detail": m.DetailParameters,
    "deliveries": m.DeliveryParameters,
    "deliveries.detail": m.DetailParameters,
    "geo.area": m.DetailParameters,
    "quality.venues": m.VenueQualityParameters,
}
for section in entities.SECTIONS:
    MODELS[section] = m.EntityParameters
    MODELS[section + ".detail"] = m.EntityDetailParameters
for kind in queues.QUEUE_SQL:
    MODELS["queues." + kind] = m.QueueParameters


def build(view: str, params: Any, settings: Settings, now: datetime) -> list[Source]:
    """Only validated registered models enter; no HTTP dictionary/identifier passthrough."""
    if view == "activity":
        params = ActivityFilters.model_validate(params.model_dump(exclude={"as_of"}))
    elif view == "findings":
        params = FindingFilters.model_validate(params.model_dump(exclude={"as_of"}))
    sources: list[Source] = []
    geo = getattr(params, "geo_scope_id", None)
    # Definition-only placeholder. No fabricated geometry is executable/copyable.
    wkb = b"" if geo is not None else None
    geo_dependencies = ("geo.area: Geometrie aus der Admin-Ablage erforderlich.",) if geo else ()
    tz = settings.uranus_timestamp_timezone
    if tz is None:
        from app.errors import APIError

        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")

    def add(
        name: str,
        query: ReadQuery,
        datasource: Literal["uranus", "admin"],
        ref: str,
        columns: tuple[str, ...] = (),
        dependencies: tuple[str, ...] = (),
        title: str = "",
    ) -> None:
        sources.append(
            Source(
                view + "." + name,
                title or name.replace("_", " "),
                datasource,
                render(query, columns, template=bool(dependencies)),
                ref,
                dependencies,
            )
        )

    def group(
        queries: dict[str, ReadQuery],
        datasource: Literal["uranus", "admin"],
        ref: str,
        columns: dict[str, tuple[str, ...]] | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> None:
        for name, query in queries.items():
            add(name, query, datasource, ref, (columns or {}).get(name, ()), dependencies)

    def previews(dependency: str, items: list[dict[str, Any]] | None = None) -> None:
        add(
            "previews",
            preview_query(items or [], settings, now),
            "uranus",
            "app.repositories.activity_previews.preview_query",
            PREVIEW_COLUMNS,
            () if items else (dependency,),
        )

    def suggestions() -> None:
        add(
            "suggestions",
            suggestions_query([]),
            "admin",
            "app.api.findings.suggestions_query",
            dependencies=("Ort-Findings der tatsächlich zurückgegebenen Seite.",),
        )

    if geo:
        add(
            "geo_area",
            geo_scope_query(geo),
            "admin",
            "app.services.geo.scopes.geo_scope_query",
            (
                "id",
                "source",
                "source_type",
                "source_id",
                "name",
                "display_name",
                "country_code",
                "admin_level",
                "kind",
                "provider_class",
                "provider_type",
                "provider_addresstype",
                "hierarchy",
                "fetched_at",
                "bbox",
                "ewkb",
            ),
        )

    if geo and view in {"dashboard", "quality", "findings"}:
        for kind in sorted(SPATIAL_TYPES):
            add(
                "membership_" + kind,
                membership_query(kind, [], b""),
                "uranus",
                "app.services.geo.membership.membership_query",
                dependencies=(
                    "Entitäten-IDs des aktuellen Findings-Batches und gespeicherte Geo-Grenze.",
                ),
            )

    if view in {"dashboard", "quality"}:
        window = period_window(params.period, now, settings.admin_timezone)
        group(
            dashboard.new_record_queries(window, tz, wkb),
            "uranus",
            "app.repositories.dashboard.new_record_queries",
            {"new_records": ("kind", "count"), "unknown_images": ("count",)},
            geo_dependencies,
        )
        if params.mode == "persisted":
            if geo:
                add(
                    "quality_membership_scan",
                    checks.spatial_stored_query([finding.c.status != "resolved"]),
                    "admin",
                    "app.services.checks.spatial_stored_query",
                )
            else:
                add(
                    "quality_counts",
                    checks.persisted_count_query(),
                    "admin",
                    "app.services.checks.persisted_count_query",
                )
            if view == "dashboard":
                preview = FindingFilters(
                    active_only=True, page_size=4, severity=params.severity, geo_scope_id=geo
                )
                if geo:
                    add(
                        "preview_membership_scan",
                        checks.spatial_stored_query(checks.persisted_conditions(preview)),
                        "admin",
                        "app.services.checks.spatial_stored_query",
                    )
                else:
                    group(
                        {
                            "preview_" + key: value
                            for key, value in checks.persisted_queries(preview).items()
                        },
                        "admin",
                        "app.services.checks.persisted_queries",
                    )
            if view == "dashboard":
                suggestions()
            group(
                dashboard.check_status_queries(),
                "admin",
                "app.repositories.dashboard.check_status_queries",
            )
        else:
            live_sources(add, settings, now)
    elif view == "activity":
        query_group, _, _ = activity.activity_queries(settings, params, now, wkb)
        group(
            query_group,
            "uranus",
            "app.repositories.activity.activity_queries",
            {"unknown": ("count",), "count": ("count",), "records": ENTITY_COLUMNS},
            geo_dependencies,
        )
        previews("Identitäten aus activity.records; keine erfundenen Preview-Parameter.")
    elif view == "findings":
        if params.mode == "persisted":
            if geo:
                add(
                    "membership_scan",
                    checks.spatial_stored_query(checks.persisted_conditions(params)),
                    "admin",
                    "app.services.checks.spatial_stored_query",
                )
            else:
                group(
                    checks.persisted_queries(params),
                    "admin",
                    "app.services.checks.persisted_queries",
                )
        else:
            live_sources(add, settings, now)
        suggestions()
    elif view in entities.SECTIONS:
        kind = entities.SECTIONS[view]
        group(
            entities.entity_page_queries(settings, cast(EntitySection, view), params, now, wkb),
            "uranus",
            "app.repositories.entities.entity_page_queries",
            {"count": ("count",), "records": ENTITY_COLUMNS},
            geo_dependencies,
        )
        add(
            "facts",
            ReadQuery(text(entities.FACTS[kind]), {"ids": []}),
            "uranus",
            "app.repositories.entities.FACTS",
            dependencies=("UUIDs aus records; erst nach der Hauptquery bekannt.",),
        )
        previews("Identitäten aus records.")
        workflow_sources(add, kind, [])
    elif view.endswith(".detail") and view.split(".")[0] in entities.SECTIONS:
        section = view.split(".")[0]
        kind = entities.SECTIONS[section]
        group(
            entities.entity_detail_queries(
                settings, cast(EntitySection, section), params.id, params.related_page, now
            ),
            "uranus",
            "app.repositories.entities.entity_detail_queries",
            {"record": ENTITY_COLUMNS, "related_count": ("count",), "related": ENTITY_COLUMNS},
        )
        add(
            "facts",
            ReadQuery(text(entities.FACTS[kind]), {"ids": [params.id]}),
            "uranus",
            "app.repositories.entities.FACTS",
        )
        previews("", [{"entity_type": kind, "entity_key": str(params.id)}])
        add(
            "related_previews",
            preview_query([], settings, now),
            "uranus",
            "app.repositories.activity_previews.preview_query",
            PREVIEW_COLUMNS,
            ("Identitäten aus related; konditional bei vorhandener Hauptentität.",),
        )
        workflow_sources(add, kind, [str(params.id)])
    elif view.startswith("queues."):
        kind = view.split(".")[1]
        group(
            queues.queue_page_queries(cast(QueueKind, kind), params, now, tz),
            "uranus",
            "app.repositories.queues.queue_page_queries",
            {"count": ("count",), "records": projection_columns(queues.QUEUE_SQL[kind])},
        )
    elif view == "checks":
        group(
            {
                "count": ReadQuery(check_api.check_count_query()),
                "records": ReadQuery(check_api.check_list_query(params.page, params.page_size)),
            },
            "admin",
            "app.api.checks",
        )
    elif view == "checks.detail":
        add(
            "record",
            ReadQuery(check_api.check_detail_query(params.id)),
            "admin",
            "app.api.checks.check_detail_query",
        )
    elif view == "marks":
        group(marks.mark_queries(params), "admin", "app.services.marks.mark_queries")
    elif view == "marks.detail":
        group(
            {
                "record": ReadQuery(marks.mark_detail_query(params.id)),
                "events": ReadQuery(marks.mark_events_query(params.id)),
            },
            "admin",
            "app.services.marks",
        )
    elif view in {"geocoding", "geocoding.detail"}:
        if view == "geocoding":
            group(
                geocode.geocode_queries(params), "admin", "app.repositories.geocode.geocode_queries"
            )
        else:
            add(
                "record",
                ReadQuery(geocode.geocode_detail_query(params.id)),
                "admin",
                "app.repositories.geocode.geocode_detail_query",
            )
        for kind in ("organization", "venue"):
            add(
                "source_" + kind,
                source_query(kind, ids=[]),
                "uranus",
                "app.repositories.geocode_sources.source_query",
                dependencies=(
                    "Entitätenschlüssel aus Admin-Aufträgen; aktuelle Adresse/point_missing.",
                ),
            )
        add(
            "candidates",
            geocode.candidate_query([]),
            "admin",
            "app.repositories.geocode.candidate_query",
            dependencies=(
                (
                    "request_id UND generation aus aktuellen Aufträgen; Vorschläge werden "
                    "zusätzlich auf stale geprüft."
                ),
            ),
        )
    elif view == "statistics":
        window = statistics_window(params, now, settings.admin_timezone)
        interval = automatic_interval(window) if params.interval == "auto" else params.interval
        windows = bucket_windows(window, interval, settings.admin_timezone)
        columns = ("entity_type", "start_at", "end_at", "count")
        add(
            "aggregation",
            statistics.aggregate_query(windows, tz, wkb),
            "uranus",
            "app.repositories.statistics.aggregate_query",
            columns,
            geo_dependencies,
        )
        if params.compare:
            add(
                "previous",
                statistics.aggregate_query([previous_window(window)], tz, wkb),
                "uranus",
                "app.repositories.statistics.aggregate_query",
                columns,
                geo_dependencies,
            )
        add(
            "recent",
            statistics.recent_query(window, tz, wkb),
            "uranus",
            "app.repositories.statistics.recent_query",
            dependencies=geo_dependencies,
        )
    elif view == "statistics.content":
        content_window = (
            None
            if params.period == "all"
            else period_window(params.period, now, settings.admin_timezone)
        )
        previous = previous_window(content_window) if content_window and params.compare else None
        add(
            "content",
            event_content.event_content_query(content_window, previous, tz, params.status, wkb),
            "uranus",
            "app.repositories.event_content.event_content_query",
            (
                "window_id",
                "dimension",
                "event_count",
                "with_assignment",
                "distinct_assignments",
                "id",
                "name",
                "rank",
                "assigned_count",
                "previous_rank",
                "previous_assigned_count",
                "previous_total",
                "previous_with_assignment",
            ),
            geo_dependencies,
        )
    elif view == "search":
        add(
            "records",
            entity_search.global_search_query(params),
            "uranus",
            "app.repositories.entity_search.global_search_query",
        )
    elif view == "entity-search":
        add(
            "records",
            entity_search.entity_search_query(params, settings, now, wkb),
            "uranus",
            "app.repositories.entity_search.entity_search_query",
            dependencies=geo_dependencies,
        )
    elif view == "graph.search":
        add(
            "records",
            graph.graph_search_query(params, wkb),
            "uranus",
            "app.repositories.graph.graph_search_query",
            dependencies=geo_dependencies,
        )
    elif view == "graph":
        root = f"{params.root_type}:{params.root_key}"
        query = graph.node_query({root})
        add(
            "root",
            query,
            "uranus",
            "app.repositories.graph.node_query",
            (
                "entity_type",
                "entity_key",
                "entity_name",
                "organization_id",
                "organization_name",
                "created_at",
                "status",
                "venue_scope",
            ),
        )
        bound: dict[str, list[str]] = {kind: [] for kind in graph.TYPES}
        bound[params.root_type] = [str(params.root_key)]
        add(
            "adjacency",
            ReadQuery(
                text(graph.ADJACENCY_SQL),
                {**bound, "relation": params.relation_type, "limit": graph.MAX_EDGES + 1},
            ),
            "uranus",
            "app.repositories.graph.ADJACENCY_SQL",
            ("type", "source", "target"),
        )
        add(
            "frontier",
            graph.node_query(
                {kind + ":00000000-0000-0000-0000-000000000000" for kind in graph.TYPES}
            ),
            "uranus",
            "app.repositories.graph.node_query",
            (
                "entity_type",
                "entity_key",
                "entity_name",
                "organization_id",
                "organization_name",
                "created_at",
                "status",
                "venue_scope",
            ),
            (
                (
                    "Weitere Knoten-IDs entstehen aus adjacency; BFS wiederholt diese Gruppe "
                    "bis zur gewählten Tiefe."
                ),
            ),
        )
        previews("Knoten des fertig begrenzten Graphen, nicht nur der Wurzel.")
    elif view == "notifications":
        group(
            notification_api.notification_queries(
                params.status,
                params.notification_type,
                params.organization_id,
                params.days,
                params.page,
                params.page_size,
                now,
                settings.admin_timezone,
            ),
            "admin",
            "app.api.notifications.notification_queries",
        )
        add(
            "source_capability",
            capability_query(),
            "uranus",
            "app.services.notifications.config.capability_query",
            ("exists",),
        )
        add(
            "source_configuration",
            organization_config_query(None, None),
            "uranus",
            "app.services.notifications.config.organization_config_query",
            ("uuid", "name", "notifications"),
            (
                (
                    "Optionales JSON-Feld erst nach Capability-Prüfung; Konfigurationswerte "
                    "werden nicht zur SQL-Ausführung freigegeben."
                ),
            ),
        )
    elif view == "deliveries":
        group(
            notification_api.delivery_queries(
                params.status,
                params.delivery_kind,
                params.organization_id,
                params.days,
                params.page,
                params.page_size,
                now,
            ),
            "admin",
            "app.api.notifications.delivery_queries",
        )
    elif view == "notifications.detail":
        group(
            {
                "record": ReadQuery(notification_api.notification_detail_query(params.id)),
                "deliveries": ReadQuery(notification_api.notification_deliveries_query(params.id)),
            },
            "admin",
            "app.api.notifications",
        )
    elif view == "deliveries.detail":
        group(
            {
                "record": ReadQuery(notification_api.delivery_detail_query(params.id)),
                "notifications": ReadQuery(
                    notification_api.delivery_notifications_query(params.id)
                ),
                "retries": ReadQuery(notification_api.delivery_retries_query(params.id)),
            },
            "admin",
            "app.api.notifications",
        )
    elif view == "geo.area":
        add(
            "record",
            geo_scope_query(params.id),
            "admin",
            "app.services.geo.scopes.geo_scope_query",
            (
                "id",
                "source",
                "source_type",
                "source_id",
                "name",
                "display_name",
                "country_code",
                "admin_level",
                "kind",
                "provider_class",
                "provider_type",
                "provider_addresstype",
                "hierarchy",
                "fetched_at",
                "bbox",
                "ewkb",
            ),
        )
    elif view == "quality.venues":
        from app.repositories.venues import venue_queries

        group(
            venue_queries(settings, params, now),
            "uranus",
            "app.repositories.venues.venue_queries",
            {
                "count": ("count",),
                "records": (
                    "uuid",
                    "name",
                    "org_uuid",
                    "organization_name",
                    "street",
                    "house_number",
                    "postal_code",
                    "city",
                    "country",
                    "upcoming_event_date_count",
                    "upcoming_published_event_date_count",
                    "soon_published_event_date_count",
                ),
            },
        )
    else:
        raise ValueError("Unregistered provenance view")
    return sources


def workflow_sources(add: Any, kind: str, keys: list[str]) -> None:
    for table, name in ((finding, "finding_count"), (record_mark, "mark_count")):
        conditions = [table.c.entity_type == kind, table.c.entity_key.in_(keys)]
        if table is finding:
            conditions.append(table.c.status != "resolved")
        add(
            name,
            entities.workflow_count_query(table, conditions),
            "admin",
            "app.repositories.entities.workflow_count_query",
            dependencies=() if keys else ("Entity-Keys der Hauptseite.",),
        )


def live_sources(add: Any, settings: Settings, now: datetime) -> None:
    for kind, sql in SOURCE_QUERIES.items():
        add(
            "snapshot_" + kind,
            ReadQuery(text(sql)),
            "uranus",
            "app.repositories.quality_sources.SOURCE_QUERIES",
        )
    for kind, sql in queues.QUEUE_SQL.items():
        add(
            "snapshot_queue_" + kind,
            ReadQuery(text(sql)),
            "uranus",
            "app.repositories.queues.QUEUE_SQL",
        )
    # Specialized venue scan participates in the live engine in addition to snapshots.
    # Its date parameters are supplied by build's shared time context separately.

    from app.repositories.venues import QUALITY_SQL, query_parameters

    add(
        "snapshot_missing_geolocation",
        ReadQuery(text(QUALITY_SQL), query_parameters(settings, now)),
        "uranus",
        "app.repositories.venues.QUALITY_SQL",
        (
            "uuid",
            "name",
            "org_uuid",
            "organization_name",
            "street",
            "house_number",
            "postal_code",
            "city",
            "country",
            "upcoming_event_date_count",
            "upcoming_published_event_date_count",
            "soon_published_event_date_count",
        ),
    )
