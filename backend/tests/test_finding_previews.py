"""Page-local image enrichment shares source identities and never changes review evidence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, text

from app.schemas.finding import Finding
from app.services.finding_previews import enrich_images, image_identities
from tests.conftest import uid

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def finding(kind="event_date", key=None, **extra):
    return Finding(
        id=f"rule:{kind}:{key}",
        rule="synthetic_rule",
        severity="warning",
        priority=4,
        priority_score=3000,
        priority_reasons=["severity_warning"],
        entity_type=kind,
        entity_key=key or str(uid(40)),
        entity_name="Synthetic record",
        organization_id=None,
        organization_name=None,
        field="title",
        message="Synthetic finding",
        last_seen_at=NOW,
        **extra,
    )


async def test_batch_deduplicates_only_valid_supported_identities(monkeypatch, settings):
    settings.uranus_api_url = "https://api.kulturbytes.de"
    items = [
        finding(),
        finding(status="resolved"),
        finding("event_link", "composite:opaque"),
        finding("venue", "invalid"),
        finding("organization", str(uid(10))),
    ]
    original = [item.model_dump(exclude={"image_url"}) for item in items]
    url = f"https://api.kulturbytes.de/api/image/{uid(60)}?width=320"
    previews = AsyncMock(
        return_value={
            ("event_date", str(uid(40))): {"image_url": url, "email": "not-copied@example.invalid"},
        }
    )
    monkeypatch.setattr("app.services.finding_previews.activity_previews", previews)
    connection = object()
    await enrich_images(connection, settings, items, NOW)
    previews.assert_awaited_once_with(
        connection,
        settings,
        [
            {"entity_type": "event_date", "entity_key": str(uid(40))},
            {"entity_type": "organization", "entity_key": str(uid(10))},
        ],
        NOW,
    )
    assert [item.image_url for item in items] == [url, url, None, None, None]
    assert [item.model_dump(exclude={"image_url"}) for item in items] == original


@pytest.mark.parametrize("items", [[], [finding("license", "opaque")], [finding("venue", "bad")]])
async def test_empty_or_unsupported_page_never_queries_source(monkeypatch, settings, items):
    settings.uranus_api_url = "https://api.kulturbytes.de"
    previews = AsyncMock()
    monkeypatch.setattr("app.services.finding_previews.activity_previews", previews)
    await enrich_images(object(), settings, items, NOW)
    previews.assert_not_awaited()


def test_local_source_cannot_link_public_production_images(settings):
    assert image_identities([finding()], settings) == []


async def test_shared_source_mapping_in_one_query(db_connection, settings):
    settings.uranus_api_url = "https://api.kulturbytes.de"
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image_link "
            "(context,context_uuid,identifier,pluto_image_uuid) VALUES "
            "('event',:event,'main',:image),('organization',:org,'main_logo',:image),"
            "('venue',:venue,'main_photo',:image)"
        ),
        {"event": uid(30), "org": uid(10), "venue": uid(20), "image": uid(60)},
    )
    items = [
        finding(kind, str(uid(key)))
        for kind, key in [
            ("event", 30),
            ("event_date", 40),
            ("organization", 10),
            ("venue", 20),
            ("image", 60),
            ("user", 1),
            ("space", 25),
            ("venue", 999999),
        ]
    ]
    statements = []

    def capture(*args):
        statements.append(args[2])

    event.listen(db_connection.sync_connection, "before_cursor_execute", capture)
    try:
        await enrich_images(db_connection, settings, items, NOW)
    finally:
        event.remove(db_connection.sync_connection, "before_cursor_execute", capture)
    assert len(statements) == 1
    assert [item.image_url for item in items] == [
        *[f"https://api.kulturbytes.de/api/image/{uid(60)}?width=320"] * 5,
        f"https://api.kulturbytes.de/api/user/{uid(1)}/avatar/128",
        None,
        None,
    ]


@pytest.mark.parametrize("mode", ["live", "persisted"])
async def test_api_enriches_both_modes_without_changing_pagination(
    client, settings, headers, monkeypatch, mode
):
    from contextlib import asynccontextmanager

    from app.api import findings as api
    from app.schemas.finding import FindingPage, Pagination

    settings.uranus_api_url = "https://api.kulturbytes.de"
    page = FindingPage(
        items=[finding()],
        mode=mode,
        observed_at=NOW,
        pagination=Pagination(page=2, page_size=1, total=9, pages=9),
    )
    source = object()
    opened = []

    async def source_connection(request):
        opened.append(source)
        yield source

    @asynccontextmanager
    async def admin_connection(request):
        yield object()

    live = AsyncMock(return_value=page)
    persisted = AsyncMock(return_value=page)
    preview = AsyncMock(
        return_value={
            ("event_date", str(uid(40))): {
                "image_url": f"https://api.kulturbytes.de/api/image/{uid(60)}?width=320"
            }
        }
    )
    monkeypatch.setattr(api, "get_connection", source_connection)
    monkeypatch.setattr(api, "connect_admin", admin_connection)
    monkeypatch.setattr(api, "get_findings", live)
    monkeypatch.setattr(api, "persisted_page", persisted)
    monkeypatch.setattr("app.services.finding_previews.activity_previews", preview)
    response = await client.get(f"/api/v1/findings?mode={mode}&page=2&page_size=1", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["image_url"].endswith(f"{uid(60)}?width=320")
    assert payload["mode"] == mode
    assert payload["pagination"] == {"page": 2, "page_size": 1, "total": 9, "pages": 9}
    assert opened == [source]
    assert preview.await_count == 1
    if mode == "persisted":
        live.assert_not_awaited()
    else:
        persisted.assert_not_awaited()


async def test_image_is_not_stored_as_finding_evidence(admin_store):
    from sqlalchemy import select

    from app.admin_tables import finding as finding_table
    from app.services.checks import persist_results
    from app.services.quality.core import RuleResult

    item = finding(image_url=f"https://api.kulturbytes.de/api/image/{uid(60)}?width=320")
    result = RuleResult(item.rule, [item], {(item.entity_type, item.entity_key)})
    async with admin_store.begin():
        await persist_results(admin_store, [result], NOW)
    metadata = (await admin_store.execute(select(finding_table.c.metadata))).scalar_one()
    assert "image_url" not in metadata["finding"]
    assert "image_url" not in metadata["evidence"]
