from datetime import timedelta

import pytest
from sqlalchemy import text

from app.repositories.quality_sources import load_sources
from app.services.quality.core import CORE_RULES, evaluate_core
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


async def test_space_override_checks_public_inheritance(db_connection, settings, now):
    sources = await load_sources(db_connection)
    event = next(e for e in sources.rows["event"] if e["uuid"] == uid(30))
    event["space_uuid"] = uid(25)
    result = evaluate_core("event_date_space_venue_mismatch", sources, settings, now)
    assert {f.entity_key for f in result.findings} == {str(uid(42))}
    assert result.findings[0].metadata["inheritance"] == "public_projection_coalesce"
    sources.rows["space"].append(
        {"uuid": uid(26), "venue_uuid": uid(21), "name": "Other", "web_link": None}
    )
    next(d for d in sources.rows["event_date"] if d["uuid"] == uid(42))["space_uuid"] = uid(26)
    assert not evaluate_core("event_date_space_venue_mismatch", sources, settings, now).findings


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
