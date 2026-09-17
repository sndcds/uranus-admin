from datetime import timedelta

import pytest
from sqlalchemy import text

from app.repositories.quality_sources import Sources, load_sources
from app.services.quality.core import CORE_RULES, QualityContext, effective_location, evaluate_core
from app.services.quality.urls import url_problem, valid_online
from tests.conftest import uid


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("https://example.org", None),
        (" HTTP://example.org/path ", None),
        ("example.org/path", "missing_scheme"),
        ("example.org:8080/path", "missing_scheme"),
        ("javascript:alert(1)", "disallowed_scheme"),
        ("ftp://example.org", "disallowed_scheme"),
        ("https://", "missing_host"),
        ("https://exa mple.org", "embedded_whitespace"),
        ("https://example.org/a\nb", "embedded_whitespace"),
        ("https://[bad", "parse_error"),
        ("https://example.org:invalid", "parse_error"),
        ("https://example.org/%qq", "parse_error"),
        ("https://example.org:99999", "parse_error"),
    ],
)
def test_url_reason(value, expected):
    assert url_problem(value) == expected
    assert valid_online(value) == bool(value and value.strip() and expected is None)


async def test_each_url_source_field_and_stable_identity(db_connection, settings, now):
    from app.services.quality.core import URL_FIELDS

    sources = await load_sources(db_connection)
    sources.rows["event_link"] = [{"id": 1, "event_uuid": uid(30), "url": None}]
    sources.rows["license"] = [{"key": "example:license", "url": None}]
    for kind, fields in URL_FIELDS.items():
        for field in fields:
            row = sources.rows[kind][0]
            previous = row[field]
            row[field] = "broken.example"
            result = evaluate_core("url_syntax", sources, settings, now)
            match = [f for f in result.findings if f.entity_type == kind and f.field == field]
            assert len(match) == 1 and match[0].metadata["reason"] == "missing_scheme"
            assert [f.id for f in result.findings] == [
                f.id for f in evaluate_core("url_syntax", sources, settings, now).findings
            ]
            row[field] = previous


async def test_events_without_dates_and_per_date_location(db_connection, settings, now):
    sources = await load_sources(db_connection)
    sources.rows["event_date"] = [
        d for d in sources.rows["event_date"] if d["event_uuid"] != uid(30)
    ]
    result = evaluate_core("event_without_dates", sources, settings, now)
    assert result.findings[0].severity == "error" and result.findings[0].entity_key == str(uid(30))
    event = sources.rows["event"][0]
    event["venue_uuid"] = None
    event["online_link"] = "https://"
    assert len(evaluate_core("event_without_location", sources, settings, now).findings) == 1
    event["online_link"] = "https://example.org"
    assert not evaluate_core("event_without_location", sources, settings, now).findings
    sources = await load_sources(db_connection)
    event = next(e for e in sources.rows["event"] if e["uuid"] == uid(30))
    event["venue_uuid"] = None
    event["online_link"] = "broken.example"
    result = evaluate_core("event_date_without_location", sources, settings, now)
    assert str(uid(40)) in {f.entity_key for f in result.findings}
    assert str(uid(42)) not in {f.entity_key for f in result.findings}
    event["online_link"] = "https://example.org"
    assert not evaluate_core("event_date_without_location", sources, settings, now).findings


@pytest.mark.parametrize(
    "event,date,expected",
    [
        (
            {"venue_uuid": uid(20), "space_uuid": uid(25)},
            {"venue_uuid": None, "space_uuid": None},
            (uid(20), uid(25)),
        ),
        (
            {"venue_uuid": uid(20), "space_uuid": uid(25)},
            {"venue_uuid": None, "space_uuid": uid(27)},
            (uid(20), uid(27)),
        ),
        (
            {"venue_uuid": uid(20), "space_uuid": uid(25)},
            {"venue_uuid": uid(21), "space_uuid": None},
            (uid(21), None),
        ),
        (
            {"venue_uuid": uid(20), "space_uuid": uid(25)},
            {"venue_uuid": uid(21), "space_uuid": uid(26)},
            (uid(21), uid(26)),
        ),
        (
            {"venue_uuid": None, "space_uuid": None},
            {"venue_uuid": None, "space_uuid": None},
            (None, None),
        ),
        ({}, {"venue_uuid": None, "space_uuid": None}, (None, None)),
    ],
    ids=[
        "inherit-both",
        "override-space",
        "override-venue",
        "override-both",
        "null-values",
        "missing-event",
    ],
)
def test_effective_location(event, date, expected):
    assert effective_location(date, event) == expected


@pytest.mark.parametrize(
    "venue_id,space_id,effective_venue_id,effective_space_id,mismatch",
    [
        pytest.param(21, None, 21, None, False, id="venue-override-clears-inherited-space"),
        pytest.param(21, 25, 21, 25, True, id="venue-override-with-mismatched-explicit-space"),
        pytest.param(21, 26, 21, 26, False, id="venue-override-with-matching-explicit-space"),
        pytest.param(None, None, 20, 25, False, id="inherit-event-venue-and-space"),
        pytest.param(None, 27, 20, 27, False, id="space-only-override-matches-inherited-venue"),
        pytest.param(None, 26, 20, 26, True, id="space-only-override-mismatches-inherited-venue"),
    ],
)
async def test_space_override_checks_public_inheritance(
    db_connection,
    settings,
    now,
    venue_id,
    space_id,
    effective_venue_id,
    effective_space_id,
    mismatch,
):
    sources = await load_sources(db_connection)
    event = next(e for e in sources.rows["event"] if e["uuid"] == uid(30))
    event["space_uuid"] = uid(25)
    sources.rows["space"].extend(
        [
            {"uuid": uid(26), "venue_uuid": uid(21), "name": "Other", "web_link": None},
            {"uuid": uid(27), "venue_uuid": uid(20), "name": "Second", "web_link": None},
        ]
    )
    date = next(d for d in sources.rows["event_date"] if d["uuid"] == uid(42))
    date["venue_uuid"] = uid(venue_id) if venue_id is not None else None
    date["space_uuid"] = uid(space_id) if space_id is not None else None

    result = evaluate_core("event_date_space_venue_mismatch", sources, settings, now)
    assert {f.entity_key for f in result.findings} == ({str(uid(42))} if mismatch else set())
    assert ("event_date", str(uid(42))) in result.covered
    if mismatch:
        assert result.findings[0].severity == "error"
        assert result.findings[0].message == (
            "Raum gehört nicht zum wirksamen Venue der öffentlichen Projektion."
        )
        assert result.findings[0].metadata["inheritance"] == "event_date_location_override"
        assert result.findings[0].metadata["effective_venue"] == str(uid(effective_venue_id))
        assert result.findings[0].metadata["effective_space"] == str(uid(effective_space_id))

    # Isolate this date so other dates cannot hide wrongly inherited relevance flags.
    context = QualityContext(Sources({**sources.rows, "event_date": [date]}), settings, now)
    for kind, expected_id in [("venue", effective_venue_id), ("space", effective_space_id)]:
        for row in sources.rows[kind]:
            relevant = expected_id is not None and row["uuid"] == uid(expected_id)
            assert context.relevance(kind, row) == dict.fromkeys(
                ("published", "upcoming", "soon"), relevant
            )
    if effective_space_id is None:
        assert context.flags[("space", "None")] == {
            "published": True,
            "upcoming": True,
            "soon": True,
        }


async def test_image_rules_and_grace_period(db_connection, settings, now):
    sources = await load_sources(db_connection)
    sources.rows["image_link"] = [
        {
            "context": "venue",
            "context_uuid": uid(999),
            "identifier": "main_logo",
            "pluto_image_uuid": None,
        },
        {
            "context": "alien",
            "context_uuid": uid(20),
            "identifier": "main",
            "pluto_image_uuid": uid(60),
        },
        {
            "context": "venue",
            "context_uuid": uid(20),
            "identifier": "bad",
            "pluto_image_uuid": uid(60),
        },
    ]
    for rule in [
        "image_link_without_image",
        "image_link_unknown_context",
        "image_link_invalid_identifier",
        "image_link_missing_target",
    ]:
        assert len(evaluate_core(rule, sources, settings, now).findings) == 1
    sources.rows["image"] = [
        {"uuid": uid(60), "created_at": (now - timedelta(days=10)).replace(tzinfo=None)},
        {"uuid": uid(61), "created_at": None},
        {"uuid": uid(62), "created_at": (now - timedelta(hours=49)).replace(tzinfo=None)},
        {"uuid": uid(63), "created_at": (now - timedelta(hours=48)).replace(tzinfo=None)},
    ]
    result = evaluate_core("image_orphaned_upload", sources, settings, now)
    assert [f.entity_key for f in result.findings] == [str(uid(62))]
    assert result.findings[0].severity == "info"


async def test_rules_cover_clean_objects_and_source_sql(db_connection, settings, now):
    sources = await load_sources(db_connection)
    sources.rows["image_link"] = [
        {
            "context": kind,
            "context_uuid": row["uuid"],
            "identifier": "main_logo",
            "pluto_image_uuid": uid(60),
        }
        for kind in ("venue", "organization")
        for row in sources.rows[kind]
    ]
    for rule in CORE_RULES:
        result = evaluate_core(rule, sources, settings, now)
        assert result.success and not result.findings
    await db_connection.execute(
        text("UPDATE uranus.event SET online_link='bad' WHERE uuid=:id"), {"id": uid(30)}
    )
    result = evaluate_core("url_syntax", await load_sources(db_connection), settings, now)
    assert result.findings[0].entity_key == str(uid(30))
    assert ("event", str(uid(31))) in result.covered


@pytest.mark.parametrize(
    "value",
    ["https://<bad>", "https://-bad.example", "https://example..org", "https://example.org/\x00"],
)
def test_malformed_hosts_and_controls(value):
    assert url_problem(value) == "parse_error"


async def test_url_venue_relevance_matches_geolocation(db_connection, settings, now):
    from app.repositories.venues import list_missing_geolocation
    from app.schemas.finding import FindingFilters
    from app.services.quality.venues import map_venue

    sources = await load_sources(db_connection)
    venue = next(v for v in sources.rows["venue"] if v["uuid"] == uid(20))
    venue["web_link"] = "bad"
    item = evaluate_core("url_syntax", sources, settings, now).findings[0]
    rows, _ = await list_missing_geolocation(db_connection, settings, FindingFilters(), now)
    assert item.priority_score == map_venue(rows[0], now).priority_score
    assert item.priority_reasons == map_venue(rows[0], now).priority_reasons


async def test_indexed_relevance_inheritance_and_publication(db_connection, settings, now):
    from app.services.quality.core import QualityContext

    sources = await load_sources(db_connection)
    event = next(e for e in sources.rows["event"] if e["uuid"] == uid(30))
    event["space_uuid"] = uid(25)
    sources.rows["space"].append(
        {"uuid": uid(26), "venue_uuid": uid(21), "name": "Override", "web_link": None}
    )
    override = next(d for d in sources.rows["event_date"] if d["uuid"] == uid(42))
    override["space_uuid"] = uid(26)
    context = QualityContext(sources, settings, now)
    for kind, key in [
        ("venue", 20),
        ("venue", 21),
        ("space", 25),
        ("space", 26),
        ("organization", 10),
    ]:
        row = next(r for r in sources.rows[kind] if r["uuid"] == uid(key))
        assert context.relevance(kind, row) == {"published": True, "upcoming": True, "soon": True}
    draft_venue = next(v for v in sources.rows["venue"] if v["uuid"] == uid(22))
    assert context.relevance("venue", draft_venue) == {
        "published": False,
        "upcoming": True,
        "soon": False,
    }
    for key, published, upcoming, soon in [
        (40, True, True, True),
        (41, True, False, False),
        (44, False, True, False),
        (45, False, True, False),
        (46, False, True, False),
        (47, False, True, False),
        (48, True, True, False),
        (49, True, True, False),
    ]:
        date = next(d for d in sources.rows["event_date"] if d["uuid"] == uid(key))
        assert context.relevance("event_date", date) == {
            "published": published,
            "upcoming": upcoming,
            "soon": soon,
        }


@pytest.mark.parametrize("size", [30, 100])
def test_quality_scan_date_work_grows_linearly(settings, size):
    from datetime import UTC, datetime

    from app.repositories.quality_sources import SOURCE_QUERIES, Sources
    from app.services.quality.core import QualityContext

    class CountedDates(list):
        visits = 0

        def __iter__(self):
            for row in super().__iter__():
                self.visits += 1
                yield row

    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    sources = Sources({kind: [] for kind in SOURCE_QUERIES})
    dates = CountedDates()
    sources.rows["event_date"] = dates
    for n in range(size):
        sources.rows["venue"].append(
            dict(uuid=uid(n + 100), name="Venue", org_uuid=None, web_link="bad", ticket_link="bad")
        )
        sources.rows["event"].append(
            dict(
                uuid=uid(n + 1000),
                name="Event",
                org_uuid=None,
                venue_uuid=uid(n + 100),
                space_uuid=None,
                release_status="released",
                source_link=None,
                online_link=None,
                ticket_link=None,
                registration_link=None,
            )
        )
        dates.append(
            dict(
                uuid=uid(n + 2000),
                event_uuid=uid(n + 1000),
                venue_uuid=None,
                space_uuid=None,
                release_status="inherited",
                start_date=now.date(),
                start_time=None,
                all_day=True,
                ticket_link=None,
            )
        )
    context = QualityContext(sources, settings, now)
    results = [evaluate_core(rule, sources, settings, now, context) for rule in CORE_RULES]
    urls = next(r for r in results if r.rule == "url_syntax")
    assert len(urls.findings) == size * 2
    assert all("published_soon" in f.priority_reasons for f in urls.findings)
    assert dates.visits <= size * 5
