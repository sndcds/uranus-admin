"""Phase 2 uses the Phase 1 polygon and real PostGIS, with separate runtime roles."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_tables import finding
from app.errors import APIError
from app.repositories.activity import activity_page
from app.repositories.geo import import_area
from app.repositories.graph import explore, search
from app.repositories.spatial import SPATIAL_TYPES
from app.schemas.activity import ActivityFilters
from app.schemas.event_content import EventContentFilters
from app.schemas.finding import FindingFilters
from app.schemas.graph import GraphFilters, GraphSearchFilters
from app.schemas.statistics import StatisticsFilters
from app.services.checks import persist_results, persisted_counts, persisted_page
from app.services.dashboard import get_summary
from app.services.event_content import get_event_content
from app.services.geo.scopes import resolve_geo_scope
from app.services.quality.engine import get_findings, scan
from app.services.statistics import get_statistics
from tests.conftest import uid
from tests.test_geo import IDENTITY, POLYGON, provider


@pytest.fixture
async def spatial_source(db_connection, now):
    # Inside edge, outside and missing points; every inherited branch is exercised.
    for table, inside in [("organization", 10), ("venue", 20)]:
        await db_connection.execute(
            text(
                f"UPDATE uranus.{table} SET point=CASE WHEN uuid=:inside "
                "THEN ST_SetSRID(ST_Point(9,54),4326) ELSE ST_SetSRID(ST_Point(11,54),4326) END"
            ),
            {"inside": uid(inside)},
        )
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=NULL WHERE uuid=:id"), {"id": uid(22)}
    )
    await db_connection.execute(
        text("UPDATE uranus.event SET created_at=:stamp"),
        {"stamp": (now - timedelta(hours=1)).replace(tzinfo=None)},
    )
    # Additional event with in-scope default venue but no dates: must be excluded.
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event(uuid,title,org_uuid,venue_uuid,created_at) "
            "VALUES (:id,'Dateless',:org,:venue,:stamp)"
        ),
        {
            "id": uid(933),
            "org": uid(10),
            "venue": uid(20),
            "stamp": now.replace(tzinfo=None) - timedelta(hours=1),
        },
    )
    return bytes(
        (
            await db_connection.execute(
                text("SELECT ST_AsEWKB(ST_GeomFromGeoJSON(:geometry))"),
                {"geometry": json.dumps(POLYGON)},
            )
        ).scalar_one()
    )


async def test_activity_geo_count_page_unknown_and_types(
    db_connection, spatial_source, settings, now
):
    page = await activity_page(
        db_connection, settings, ActivityFilters(page_size=100), now, spatial_source
    )
    ids = {(i.entity_type, i.entity_key) for i in page.items}
    expected = {
        ("organization", str(uid(10))),
        ("venue", str(uid(20))),
        ("space", str(uid(25))),
        ("event", str(uid(30))),
        ("event", str(uid(32))),
    }
    expected |= {("event_date", str(uid(i))) for i in [40, 41, 43, 45, 46, 48, 49]}
    assert ids == expected
    for index in range(len(expected)):
        result = await activity_page(
            db_connection,
            settings,
            ActivityFilters(page=index + 1, page_size=1),
            now,
            spatial_source,
        )
        assert result.pagination.total == result.pagination.pages == len(expected)
        assert result.items[0].entity_key == page.items[index].entity_key
    # All spatial source tables require created_at; only the nonspatial image is unknown.
    unknown = await activity_page(
        db_connection, settings, ActivityFilters(timestamp_state="unknown"), now, spatial_source
    )
    assert unknown.unknown_timestamp_count == unknown.pagination.total == 0
    assert unknown.items == []
    known = await activity_page(db_connection, settings, ActivityFilters(), now, spatial_source)
    assert known.unknown_timestamp_count == 0


@pytest.mark.parametrize("kind", ["user", "image", "partner_request", "team_membership"])
async def test_nonspatial_activity_rejected(db_connection, spatial_source, settings, now, kind):
    with pytest.raises(APIError) as exc:
        await activity_page(
            db_connection,
            settings,
            ActivityFilters(entity_type=kind, geo_scope_id=uid(800)),
            now,
            spatial_source,
        )
    assert exc.value.status == 422


@pytest.mark.parametrize("old,new", [(None, 800), (800, None), (800, 801)])
async def test_activity_cursor_scope(db_connection, spatial_source, settings, now, old, new):
    filters = ActivityFilters(cursor="start", page_size=1, geo_scope_id=uid(old) if old else None)
    first = await activity_page(
        db_connection, settings, filters, now, spatial_source if old else None
    )
    filters.cursor = first.cursor_pagination.next_cursor
    next_page = await activity_page(
        db_connection, settings, filters, now, spatial_source if old else None
    )
    assert (
        next_page.items[0].entity_key != first.items[0].entity_key
        or next_page.items[0].entity_type != first.items[0].entity_type
    )
    filters.geo_scope_id = uid(new) if new else None
    with pytest.raises(APIError):
        await activity_page(db_connection, settings, filters, now, spatial_source if new else None)


async def seed_findings(admin, now):
    identities = [
        ("organization", 10),
        ("organization", 11),
        ("venue", 20),
        ("venue", 21),
        ("venue", 22),
        ("space", 25),
        ("event", 30),
        ("event", 31),
        ("event", 32),
        ("event", 933),
        ("event_date", 40),
        ("event_date", 42),
        ("event_date", 43),
        ("user", 1),
        ("venue", "technical:key"),
        ("event_link", "123"),
    ]
    async with admin.begin():
        await admin.execute(
            finding.insert(),
            [
                dict(
                    id=f"test-{i:04}",
                    rule="geo_test",
                    severity="warning",
                    entity_type=kind,
                    entity_key=str(uid(key)) if isinstance(key, int) else key,
                    field="test",
                    message="test",
                    first_seen_at=now,
                    last_seen_at=now,
                )
                for i, (kind, key) in enumerate(identities)
            ],
        )


async def test_persisted_exact_counts_pagination_and_roles(
    admin_store, db_connection, spatial_source, now, database
):
    engine = create_async_engine(database[0])
    try:
        async with engine.begin() as setup:
            await setup.execute(text("REVOKE USAGE ON SCHEMA uranus FROM admin_history_test"))
    finally:
        await engine.dispose()
    await seed_findings(admin_store, now)
    # The Admin runtime cannot query Source; give Source a role with no Admin privileges.
    await db_connection.execute(text("CREATE ROLE geo_analytics_reader_test"))
    await db_connection.execute(text("GRANT USAGE ON SCHEMA uranus TO geo_analytics_reader_test"))
    await db_connection.execute(
        text("GRANT SELECT ON ALL TABLES IN SCHEMA uranus TO geo_analytics_reader_test")
    )
    await db_connection.execute(text("SET LOCAL ROLE geo_analytics_reader_test"))
    filters = FindingFilters(page_size=2, geo_scope_id=uid(800))
    expected = [
        "test-0000",
        "test-0002",
        "test-0005",
        "test-0006",
        "test-0008",
        "test-0010",
        "test-0012",
    ]
    seen = []
    for index in range(4):
        filters.page = index + 1
        page = await persisted_page(admin_store, filters, now, db_connection, spatial_source)
        assert page.pagination.total == 7 and page.pagination.pages == 4
        seen.extend(i.id for i in page.items)
    assert seen == expected
    counts, urgent = await persisted_counts(admin_store, db_connection, spatial_source)
    assert counts.total == counts.warnings == 7
    assert counts.rule_counts["geo_test"] == 7 and urgent == 0
    with pytest.raises(DBAPIError):
        async with db_connection.begin_nested():
            await db_connection.execute(text("SELECT id FROM admin.geo_area"))
    with pytest.raises(DBAPIError):
        async with admin_store.begin(), admin_store.begin_nested():
            await admin_store.execute(text("SELECT uuid FROM uranus.venue"))


@pytest.mark.parametrize("old,new", [(None, 800), (800, None), (800, 801)])
async def test_findings_cursor_scope(admin_store, db_connection, spatial_source, now, old, new):
    await seed_findings(admin_store, now)
    filters = FindingFilters(cursor="start", page_size=2, geo_scope_id=uid(old) if old else None)
    first = await persisted_page(
        admin_store, filters, now, db_connection, spatial_source if old else None
    )
    filters.cursor = first.cursor_pagination.next_cursor
    second = await persisted_page(
        admin_store, filters, now, db_connection, spatial_source if old else None
    )
    assert not ({i.id for i in first.items} & {i.id for i in second.items})
    filters.geo_scope_id = uid(new) if new else None
    with pytest.raises(APIError):
        await persisted_page(
            admin_store, filters, now, db_connection, spatial_source if new else None
        )


async def test_findings_many_batches_exact_total_bounded_queries(
    admin_store, db_connection, spatial_source, now
):
    async with admin_store.begin():
        await admin_store.execute(
            finding.insert(),
            [
                dict(
                    id=f"large-{i:05}",
                    rule="geo_test",
                    severity="warning",
                    entity_type="venue",
                    entity_key=str(uid(20 if i % 2 else 21)),
                    field=f"field-{i}",
                    message="test",
                    first_seen_at=now,
                    last_seen_at=now,
                )
                for i in range(1201)
            ],
        )
    queries = []

    def record(conn, cursor, statement, parameters, context, many):
        queries.append(statement)

    event.listen(db_connection.sync_connection, "before_cursor_execute", record)
    try:
        result = await persisted_page(
            admin_store, FindingFilters(page=60, page_size=10), now, db_connection, spatial_source
        )
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", record)
    assert result.pagination.total == 600 and result.pagination.pages == 60
    assert len(result.items) == 10 and result.items[-1].id == "large-01199"
    assert len(queries) == 3  # one venue query per batch, not per finding


async def test_live_persisted_and_dashboard_same_membership(
    admin_store, db_connection, spatial_source, settings, now
):
    results = await scan(db_connection, settings, now)
    async with admin_store.begin():
        await persist_results(admin_store, results, now)
    live = await get_findings(
        db_connection, settings, FindingFilters(mode="live", page_size=100), now, spatial_source
    )
    persisted = await persisted_page(
        admin_store, FindingFilters(page_size=100), now, db_connection, spatial_source
    )
    assert live.pagination.total == persisted.pagination.total > 0
    assert {i.id for i in live.items} == {i.id for i in persisted.items}
    area = await import_area(admin_store, IDENTITY, provider(settings))
    geo = await resolve_geo_scope(admin_store, area.id)
    await admin_store.rollback()
    live_dashboard = await get_summary(db_connection, settings, "24h", now, geo=geo)
    saved_dashboard = await get_summary(db_connection, settings, "24h", now, admin_store, geo)
    assert live_dashboard.quality.total == saved_dashboard.quality.total == live.pagination.total
    assert live_dashboard.quality.rule_counts == saved_dashboard.quality.rule_counts
    assert saved_dashboard.check_status is not None
    for key in ["organizations", "venues", "spaces", "events", "event_dates"]:
        assert saved_dashboard.new_record_scopes[key] == "geo"
    for key in ["users", "images", "partner_requests", "team_memberships"]:
        assert saved_dashboard.new_record_scopes[key] == "global"
    global_dashboard = await get_summary(db_connection, settings, "24h", now)
    assert saved_dashboard.new_records.users == global_dashboard.new_records.users == 1
    assert saved_dashboard.new_records.organizations == 1
    assert saved_dashboard.new_records.events == 2  # includes event32 via date venue override
    assert (
        saved_dashboard.scoped_new_records_total + saved_dashboard.global_new_records_total
        == saved_dashboard.new_records.total
    )
    assert global_dashboard.scoped_new_records_total is None


async def test_statistics_geo_before_buckets_and_same_previous(
    db_connection, spatial_source, settings, now
):
    # Both current and previous contain inside+outside venues.
    for i, point in [(934, "POINT(9.5 54.5)"), (935, "POINT(11 54.5)")]:
        await db_connection.execute(
            text(
                "INSERT INTO uranus.venue(uuid,org_uuid,scope,name,point,created_at) "
                "VALUES (:id,'00000000-0000-0000-0000-00000000000a','organization',"
                "'Previous',ST_GeomFromText(:point,4326),:stamp)"
            ),
            {"id": uid(i), "point": point, "stamp": now.replace(tzinfo=None) - timedelta(hours=25)},
        )
    result = await get_statistics(
        db_connection, settings, StatisticsFilters(compare="previous"), now, spatial_source
    )
    series = {s.entity_type: s for s in result.series}
    for kind in ["organization", "venue", "space"]:
        assert series[kind].total == 1 and series[kind].scope == "geo"
    assert series["event"].total == 2
    assert series["venue"].previous_total == 1
    assert series["user"].total == 1 and series["user"].scope == "global"
    assert series["partner_request"].total == 1 and series["partner_request"].scope == "global"
    assert all(i.entity_type in SPATIAL_TYPES for i in result.recent)
    assert all(s.total == sum(p.count for p in s.points) for s in result.series)


@pytest.mark.parametrize("period", ["24h", "all"])
async def test_event_content_scopes_denominator_before_ranking(
    db_connection, spatial_source, settings, now, period
):
    # Globally dominant category99 only outside (including dateless event).
    await db_connection.execute(text("UPDATE uranus.event SET categories=ARRAY[99]"))
    await db_connection.execute(
        text("UPDATE uranus.event SET categories=ARRAY[1] WHERE uuid IN (:a,:b)"),
        {"a": uid(30), "b": uid(32)},
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event(uuid,org_uuid,title,created_at,venue_uuid,categories) "
            "VALUES (:id,'00000000-0000-0000-0000-00000000000a',"
            "'Previous inside',:stamp,:venue,ARRAY[2])"
        ),
        {"id": uid(936), "stamp": now.replace(tzinfo=None) - timedelta(hours=25), "venue": uid(20)},
    )
    await db_connection.execute(
        text("INSERT INTO uranus.event_date(uuid,event_uuid,start_date) VALUES (:id,:event,:day)"),
        {"id": uid(937), "event": uid(936), "day": now.date()},
    )
    result = await get_event_content(
        db_connection,
        settings,
        EventContentFilters(period=period, compare="previous" if period != "all" else None),
        now,
        spatial_source,
    )
    assert result.event_count == (2 if period == "24h" else 3)
    assert "99" not in {r.id for r in result.categories.items}
    assert result.categories.items[0].id == "1"
    assert result.categories.items[0].event_share_percent == (100 if period == "24h" else 66.67)
    assert result.coverage.categories.events_with_assignment == result.event_count
    if result.comparison:
        assert result.comparison.event_count == 1


async def test_graph_discovery_only(db_connection, spatial_source, settings):
    for kind, query, keys in [
        ("organization", "Organization", [10]),
        ("venue", "Venue", [20]),
        ("space", "Saal", [25]),
        ("event", "Event", [30, 32]),
        ("event_date", "Event", [40, 41, 43, 45, 46, 48, 49]),
    ]:
        result = await search(
            db_connection, GraphSearchFilters(q=query, entity_type=kind), spatial_source
        )
        assert {n.key for n in result.items} == {uid(i) for i in keys}
    with pytest.raises(APIError):
        await search(
            db_connection,
            GraphSearchFilters(q="fixture", entity_type="user", geo_scope_id=uid(800)),
            spatial_source,
        )
    graph = await explore(
        db_connection, settings, GraphFilters(root_type="venue", root_key=uid(20), depth=3)
    )
    assert any(n.key == uid(21) for n in graph.nodes)  # related outside venue retained
    outside = await explore(
        db_connection, settings, GraphFilters(root_type="venue", root_key=uid(21))
    )
    assert outside.root.key == uid(21)


@pytest.mark.parametrize(
    "endpoint",
    [
        "dashboard/activity",
        "findings",
        "dashboard/summary",
        "statistics/entities",
        "statistics/events/content",
        "graph/search?q=Venue",
    ],
)
async def test_all_endpoints_scope_validation_cached_no_provider(
    admin_store, db_client, settings, headers, endpoint
):
    area = await import_area(admin_store, IDENTITY, provider(settings))
    # Provider deliberately unconfigured. These requests only use cached geometry.
    settings.nominatim_base_url = None
    base = "/api/v1/" + endpoint + ("&" if "?" in endpoint else "?")
    assert (await db_client.get(base + "geo_scope_id=bad", headers=headers)).status_code == 422
    unknown = await db_client.get(base + f"geo_scope_id={uid(9999)}", headers=headers)
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "geo_scope_not_found"
    assert (await db_client.get(base + f"geo_scope_id={area.id}")).status_code == 401
    response = await db_client.get(base + f"geo_scope_id={area.id}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"


async def test_representative_explain(db_connection, spatial_source, settings, now, tmp_path):
    statements = []

    def record(conn, cursor, statement, parameters, context, many):
        if "geo_scope_wkb" in context.compiled_parameters[0]:
            statements.append((statement, parameters))

    event.listen(db_connection.sync_connection, "before_cursor_execute", record)
    try:
        await activity_page(db_connection, settings, ActivityFilters(), now, spatial_source)
        await get_statistics(db_connection, settings, StatisticsFilters(), now, spatial_source)
        await get_event_content(
            db_connection, settings, EventContentFilters(period="all"), now, spatial_source
        )
        await search(db_connection, GraphSearchFilters(q="Event"), spatial_source)
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", record)
    plans = []
    for sql, params in statements:
        result = await db_connection.exec_driver_sql(
            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + sql, params
        )
        plans.append({"sql": sql, "plan": result.scalar_one()})
    assert len(plans) >= 7
    (tmp_path / "geo-analytics-explain.json").write_text(json.dumps(plans, indent=2))
