from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.database import get_connection
from app.errors import APIError
from app.schemas.marks import MarkCreate, MarkFilters, MarkUpdate
from app.services.marks import create_mark, mark_page, update_mark
from tests.conftest import uid


def creation(**extra):
    return dict(entity_type="venue", entity_key=str(uid(20)), reasons=["incorrect"], **extra)


def update(item, **extra):
    body = {key: item[key] for key in ("version", "reasons", "reason_detail", "urgency", "status")}
    return {**body, **extra}


@pytest.mark.parametrize(
    "extra",
    [
        {"reasons": []},
        {"reasons": ["invented"]},
        {"reasons": ["incorrect", "incorrect"]},
        {"reasons": ["other"]},
        {"reasons": ["other"], "reason_detail": "  "},
        {"note": "  "},
        {"note": "x" * 4001},
        {"created_by": "forged"},
        {"completed_at": "2026-09-14T12:00:00Z"},
        {"urgency": "critical"},
    ],
)
def test_invalid_mark_inputs(extra):
    with pytest.raises(ValidationError):
        MarkCreate(**{**creation(), **extra})


async def test_mark_routes_require_auth_and_storage(client, headers):
    identifier = str(uuid4())
    for method, path, body in [
        ("GET", "/record-marks", None),
        ("GET", f"/record-marks/{identifier}", None),
        ("POST", "/record-marks", creation()),
        (
            "PATCH",
            f"/record-marks/{identifier}",
            {
                "version": 1,
                "reasons": ["incorrect"],
                "status": "done",
            },
        ),
    ]:
        response = await client.request(method, f"/api/v1{path}", json=body)
        assert response.status_code == 401
    response = await client.get("/api/v1/record-marks", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "admin_storage_unconfigured"


async def test_completion_reopening_and_notes_keep_authors(admin_store, db_client, headers):
    app = db_client._transport.app
    app.dependency_overrides[get_current_admin] = lambda: AdminPrincipal(subject="alice")
    response = await db_client.post(
        "/api/v1/record-marks",
        json=creation(note="Datum prüfen", urgency="urgent"),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    first = response.json()
    path = f"/api/v1/record-marks/{first['id']}"
    assert first["created_by"] == "alice" and first["events"][0]["note"] == "Datum prüfen"
    assert first["completed_at"] is None and first["status"] == "open"
    # Independent concern on the same source record.
    second = (await db_client.post("/api/v1/record-marks", json=creation(), headers=headers)).json()
    app.dependency_overrides[get_current_admin] = lambda: AdminPrincipal(subject="bob")
    response = await db_client.patch(
        path, json=update(first, status="done", note="Datum korrigiert")
    )
    assert response.status_code == 200, response.text
    done = response.json()
    assert done["completed_by"] == "bob" and done["completed_at"]
    assert done["events"][-1]["created_at"] == done["completed_at"]
    assert done["events"][-1]["kind"] == "completed"
    # A later note must not rewrite the original completion metadata.
    noted = (await db_client.patch(path, json=update(done, note="Nachkontrolle erfolgt"))).json()
    assert noted["completed_at"] == done["completed_at"] and noted["completed_by"] == "bob"
    app.dependency_overrides[get_current_admin] = lambda: AdminPrincipal(subject="carol")
    reopened = (
        await db_client.patch(path, json=update(noted, status="open", note="Erneut falsch"))
    ).json()
    assert reopened["completed_at"] is None and reopened["completed_by"] is None
    assert [event["author"] for event in reopened["events"]] == ["alice", "bob", "bob", "carol"]
    assert reopened["events"][-1]["kind"] == "reopened"
    assert reopened["events"][: len(noted["events"])] == noted["events"]
    assert noted["events"][: len(done["events"])] == done["events"]
    assert done["events"][: len(first["events"])] == first["events"]
    assert reopened["events"][1]["note"] == "Datum korrigiert"
    assert (await db_client.get(f"/api/v1/record-marks/{second['id']}")).json()["status"] == "open"
    final = (await db_client.patch(path, json=update(reopened, status="done"))).json()
    assert final["completed_by"] == "carol" and len(final["events"]) == 5
    assert [event["version"] for event in final["events"]] == [1, 2, 3, 4, 5]
    timestamps = [event["created_at"] for event in final["events"]]
    assert timestamps == sorted(timestamps)
    persisted = (await db_client.get(path)).json()
    assert persisted == final
    active = (await db_client.get("/api/v1/record-marks")).json()
    assert [item["id"] for item in active["items"]] == [second["id"]]


async def test_stale_updates_do_not_overwrite_or_append(admin_store, db_connection):
    first = await create_mark(admin_store, db_connection, MarkCreate(**creation()), "alice")
    body = update(first.model_dump(), status="done", note="Finished")
    done = await update_mark(admin_store, first.id, MarkUpdate(**body), "bob")
    with pytest.raises(APIError) as error:
        await update_mark(admin_store, first.id, MarkUpdate(**body), "carol")
    assert error.value.code == "mark_conflict"
    unchanged = await update_mark(
        admin_store, done.id, MarkUpdate(**update(done.model_dump())), "carol"
    )
    assert unchanged == done


async def test_filter_sort_pagination_and_source_identity(admin_store, db_connection):
    for urgency in ("normal", "urgent", "high"):
        await create_mark(admin_store, db_connection, MarkCreate(**creation(urgency=urgency)), "a")
    first = await mark_page(admin_store, MarkFilters(page_size=2))
    assert [item.urgency for item in first.items] == ["urgent", "high"]
    assert first.pagination.total == 3 and first.pagination.pages == 2
    assert (await mark_page(admin_store, MarkFilters(page=2, page_size=2))).items[
        0
    ].urgency == "normal"
    assert (await mark_page(admin_store, MarkFilters(reason="technical"))).pagination.total == 0
    assert (
        await mark_page(admin_store, MarkFilters(reason="incorrect", urgency="high"))
    ).pagination.total == 1
    for kind, key in [
        ("organization", str(uid(10))),
        ("space", str(uid(25))),
        ("event", str(uid(30))),
        ("event_date", str(uid(40))),
        ("user", str(uid(1))),
        ("image", str(uid(61))),
        ("partner_request", f"partner-request:{uid(10)}:{uid(11)}"),
        ("team_membership", f"membership:{uid(10)}:{uid(1)}"),
    ]:
        mark = await create_mark(
            admin_store,
            db_connection,
            MarkCreate(entity_type=kind, entity_key=key, reasons=["other"], reason_detail="Prüfen"),
            "a",
        )
        assert mark.entity_key == key
    with pytest.raises(APIError) as error:
        await create_mark(
            admin_store,
            db_connection,
            MarkCreate(entity_type="venue", entity_key=str(uid(999)), reasons=["incorrect"]),
            "a",
        )
    assert error.value.code == "record_not_found"
    assert (await mark_page(admin_store, MarkFilters(entity_type="image"))).pagination.total == 1


async def test_api_rejects_forgery_and_survives_source_outage(admin_store, db_client, headers):
    first = (await db_client.post("/api/v1/record-marks", json=creation(), headers=headers)).json()
    path = f"/api/v1/record-marks/{first['id']}"
    for forged in ({"completed_by": "fake"}, {"completed_at": "2026-01-01T00:00:00Z"}):
        assert (
            await db_client.patch(path, headers=headers, json={**update(first), **forged})
        ).status_code == 422
    assert (
        await db_client.patch(path, headers=headers, json=update(first, version=99))
    ).status_code == 409
    assert (
        await db_client.get("/api/v1/record-marks?reason=invalid", headers=headers)
    ).status_code == 422
    assert (
        await db_client.get(f"/api/v1/record-marks/{uuid4()}", headers=headers)
    ).status_code == 404

    async def unavailable():
        raise OSError("source unavailable")
        yield

    db_client._transport.app.dependency_overrides[get_connection] = unavailable
    assert (await db_client.get("/api/v1/record-marks", headers=headers)).status_code == 200
    assert (await db_client.get(path, headers=headers)).status_code == 200
    response = await db_client.patch(path, headers=headers, json=update(first, status="done"))
    assert response.status_code == 200 and response.json()["completed_by"] == "development-only"


async def test_extra_quality_source_keys(admin_store, db_connection):
    await db_connection.execute(
        text("INSERT INTO uranus.license (key, url) VALUES ('test','https://example.org')")
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_link (id,event_uuid,url) OVERRIDING SYSTEM VALUE "
            "VALUES (789,:event,'https://example.org')"
        ),
        {"event": uid(30)},
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image_link "
            "(context,context_uuid,identifier,pluto_image_uuid) "
            "VALUES ('venue',:venue,'poster',:image)"
        ),
        {"venue": uid(20), "image": uid(60)},
    )
    for kind, key in [
        ("license", "test"),
        ("event_link", "789"),
        ("image_link", f"image-link:venue:{uid(20)}:poster"),
    ]:
        result = await create_mark(
            admin_store,
            db_connection,
            MarkCreate(entity_type=kind, entity_key=key, reasons=["technical"]),
            "a",
        )
        assert result.entity_key == key


async def test_runtime_history_is_append_only_and_version_unique(admin_store, db_connection):
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from app.admin_tables import record_mark_event
    from app.services.marks import detail_in_transaction

    first = await create_mark(
        admin_store, db_connection, MarkCreate(**creation(note="Original")), "a"
    )
    for sql in (
        "UPDATE admin.record_mark_event SET note='rewritten'",
        "DELETE FROM admin.record_mark_event",
        "TRUNCATE admin.record_mark_event",
    ):
        with pytest.raises(DBAPIError):
            async with admin_store.begin():
                await admin_store.execute(text(sql))
    event = first.events[0].model_dump()
    event["id"] = uuid4()
    event["mark_id"] = first.id
    with pytest.raises(IntegrityError):
        async with admin_store.begin():
            await admin_store.execute(record_mark_event.insert().values(**event))
    async with admin_store.begin():
        assert await detail_in_transaction(admin_store, first.id) == first
