"""Structured source genres and isolated Qdrant filter/embedding regressions."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.repositories.research import rehydrate_semantic_events
from app.repositories.research_areas import ResolvedResearchAreas
from app.repositories.vector_events import TYPES_SQL, extract_events
from app.research.semantic_contracts import COLLECTIONS, EventPayload
from app.research.semantic_evidence import semantic_hits
from app.research.vector_transport import Qdrant
from app.schemas.research import SemanticResearchFilters
from app.services import semantic_search as service
from tests.conftest import uid
from tests.test_semantic_knowledge_index import MODEL, plan, sample
from tests.test_semantic_search import PATH
from tests.test_semantic_search import retrieval as retrieval_fixture
from tests.test_vector_index import vector_settings

retrieval = retrieval_fixture


@pytest.mark.parametrize(
    "links,keys,names",
    [
        ([], [], []),
        ([(1, 2, "Jazz")], ["1:2"], ["Jazz"]),
        ([(2, 2, "Rock"), (1, 2, "Jazz"), (1, 2, "Jazz")], ["1:2", "2:2"], ["Jazz", "Rock"]),
        ([(1, 0, "No genre"), (3, 9, None)], ["3:9"], []),
    ],
)
async def test_extracted_genres(settings, links, keys, names):
    async def extract(ordered):
        results = []
        for value in (
            1,
            [
                {
                    "entity_id": uid(30),
                    "organization_id": uid(10),
                    "title": "Concert",
                    "status": "released",
                    "category_ids": [5, 2, 5],
                }
            ],
            [],
            [
                {
                    "event_uuid": uid(30),
                    "type_id": t,
                    "genre_id": g,
                    "type_name": "Music",
                    "genre_name": name,
                }
                for t, g, name in ordered
            ],
        ):
            result = Mock()
            result.scalar_one.return_value = value
            result.mappings.return_value = value
            results.append(result)
        conn = AsyncMock()
        conn.execute.side_effect = results
        docs, _ = await extract_events(conn, None, settings, datetime.now(UTC), semantic=True)
        assert str(conn.execute.call_args_list[-1].args[0]) == TYPES_SQL
        return docs[0]

    doc = await extract(links)
    assert doc == await extract(list(reversed(links)))
    assert doc.payload.genre_keys == keys
    assert doc.payload.genre_names == names
    assert doc.payload.category_ids == [2, 5]
    for name in names:
        assert name in doc.sections[0].text
    assert ("Genres:" in doc.sections[0].text) == bool(names)
    assert "l.type_id,l.genre_id" in TYPES_SQL
    assert "ORDER BY l.event_uuid,l.type_id,l.genre_id" in TYPES_SQL


def test_genre_metadata_version_and_content_reconciliation():
    doc = sample("event", genre_keys=["1:2"], genre_names=["Jazz"])
    existing = {i: deepcopy(p) for i, (_, p) in plan(doc).desired.items()}
    assert (
        doc.payload.document_schema_version
        == COLLECTIONS["event"].document_version
        == "event-public-v3"
    )
    assert "Genres: Jazz" in doc.sections[0].text
    changed = sample(
        "event",
        entity_id=doc.entity_id,
        organization_id=doc.payload.organization_id,
        genre_keys=["2:2"],
        genre_names=["Jazz"],
    )
    result = plan(changed, existing)
    assert result.metadata and not result.embed and not result.delete
    renamed = sample(
        "event",
        entity_id=doc.entity_id,
        organization_id=doc.payload.organization_id,
        genre_keys=["1:2"],
        genre_names=["Jazz fusion"],
    )
    result = plan(renamed, existing)
    assert result.embed and result.delete and not result.metadata
    old = deepcopy(existing)
    for payload in old.values():
        payload["document_schema_version"] = "event-public-v2"
        del payload["genre_keys"], payload["genre_names"]
    result = plan(doc, old)
    assert result.metadata and not result.embed and not result.delete
    assert not semantic_hits(
        [{"score": 0.9, "payload": p} for p in old.values()], {doc.entity_id}, MODEL, entity="event"
    )
    with pytest.raises(ValidationError):
        EventPayload.model_validate(
            {**doc.payload.model_dump(), "document_schema_version": "event-public-v2"}
        )


@pytest.mark.parametrize(
    "keys",
    [["Jazz"], ["1:0"], ["01:2"], ["-0:2"], ["1:2147483648"], ["1:2:3"], ["1:2\n"], ["1:2"] * 51],
)
def test_genre_query_validation(keys):
    with pytest.raises(ValidationError):
        SemanticResearchFilters(q="Music", genre_keys=keys)


def test_genre_query_dedup_bounds_and_category_unchanged():
    filters = SemanticResearchFilters(q="Music", genre_keys=["2:2", "1:2", "1:2"], category=5)
    assert filters.genre_keys == ["1:2", "2:2"] and filters.category == 5
    assert SemanticResearchFilters(q="Music").genre_keys == []
    for values in ({"area_ids": [uuid4()] * 51}, {"area_id": uuid4(), "area_ids": [uuid4()]}):
        with pytest.raises(ValidationError):
            SemanticResearchFilters(q="Music", **values)


@pytest.mark.parametrize("entity", ["venue", "organization", None])
@pytest.mark.parametrize("keys", [["1:2"], []])
async def test_other_collections_reject_genres_before_network(settings, entity, keys):
    def reject(request):
        pytest.fail("Invalid collection filter must not reach Qdrant")

    q = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(reject), entity=entity)
    try:
        with pytest.raises(ValueError, match="event_collection_required"):
            await q.search([1.0] * 1024, 10, genre_keys=keys)
    finally:
        await q.http.close()


async def test_qdrant_or_within_and_across_dimensions(settings):
    areas = [uid(1), uid(2)]
    requests = []

    def serve(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {"points": []}})

    q = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity="event")
    try:
        await q.search([1.0] * 1024, 10, area_ids=areas, genre_keys=["1:2", "1:3", "1:2"])
        assert requests[0]["filter"] == {
            "must": [
                {"key": "area_ids", "match": {"any": [str(a) for a in areas]}},
                {"key": "genre_keys", "match": {"any": ["1:2", "1:3"]}},
            ]
        }
    finally:
        await q.http.close()


@pytest.mark.integration
async def test_real_qdrant_area_genre_filter(settings):
    origin = os.environ.get("TEST_QDRANT_URL")
    if not origin:
        pytest.skip("Set TEST_QDRANT_URL for isolated Qdrant integration")
    assert urlsplit(origin).hostname in {"127.0.0.1", "localhost"}
    settings = vector_settings(settings)
    settings.qdrant_url = origin
    settings.qdrant_api_key = SecretStr("vector-test-only-key-with-more-than-32-characters")
    q = Qdrant(settings, "jina-v3", entity="event")
    q.collection = "uranus_test_genres_" + uuid4().hex
    q.path = "/collections/" + q.collection
    flensburg, husum, kiel = uuid4(), uuid4(), uuid4()
    a, b, c = uuid4(), uuid4(), uuid4()
    vector = [1.0] + [0.0] * 1023
    try:
        await q.create()
        await q.upsert(
            [
                {
                    "id": str(key),
                    "vector": vector,
                    "payload": {"area_ids": [str(area)], "genre_keys": [genre]},
                }
                for key, area, genre in ((a, flensburg, "1:2"), (b, husum, "1:3"), (c, kiel, "1:2"))
            ]
        )
        for genres, expected in ((["1:2"], {a}), (["1:2", "1:3"], {a, b}), (["2:2"], set())):
            hits = await q.search(vector, 10, area_ids=[flensburg, husum], genre_keys=genres)
            assert {h["id"] for h in hits} == {str(key) for key in expected}
        assert {h["id"] for h in await q.search(vector, 10, genre_keys=["1:2"])} == {str(a), str(c)}
    finally:
        await q.http.request("DELETE", q.path, missing=True)
        await q.http.close()


@pytest.mark.integration
async def test_source_genres_translation_identity_and_current_eligibility(db_connection, settings):
    await db_connection.execute(
        text("""INSERT INTO uranus.genre_type(name,genre_id,type_id,iso_639_1)
        VALUES ('Jazz',2,1,'de'),('Jazz duplicate',2,1,'en'),('Jazz',2,1,'de'),
        ('Rock',2,2,'de'),('Ignored zero',0,1,'de')""")
    )
    await db_connection.execute(
        text("""INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id)
        VALUES (:a,1,2),(:a,2,2),(:a,1,0),(:b,2,2)"""),
        {"a": uid(30), "b": uid(32)},
    )
    docs, _ = await extract_events(db_connection, None, settings, datetime.now(UTC), semantic=True)
    doc = next(d for d in docs if d.entity_id == uid(30))
    assert doc.payload.genre_keys == ["1:2", "2:2"]
    assert doc.payload.genre_names == ["Jazz", "Rock"]
    assert "Genres: Jazz, Rock" in doc.sections[0].text
    for keys, expected in (
        (["1:2"], [uid(30)]),
        (["1:2", "2:2"], [uid(32), uid(30)]),
        (["9:2"], []),
    ):
        page = await rehydrate_semantic_events(
            db_connection,
            settings,
            SemanticResearchFilters(q="music", genre_keys=keys),
            [uid(32), uid(30)],
            datetime.now(UTC),
        )
        assert [i.entity_key for i in page.items] == expected
    await db_connection.execute(
        text("DELETE FROM uranus.event_type_link WHERE event_uuid=:id"), {"id": uid(30)}
    )
    page = await rehydrate_semantic_events(
        db_connection,
        settings,
        SemanticResearchFilters(q="music", genre_keys=["1:2"]),
        [uid(30)],
        datetime.now(UTC),
    )
    assert not page.items


@pytest.mark.parametrize("area_mode", ["none", "single", "multiple"])
async def test_api_passes_repeated_genres_to_semantic_collection(
    client, headers, retrieval, monkeypatch, settings, area_mode
):
    settings.semantic_search_url = "https://search.example.test/search"

    doc = sample("event", entity_id=uid(30), genre_keys=["1:2"], genre_names=["Jazz"])
    retrieval["hits"] = [{"score": 0.9, "payload": p} for _, p in plan(doc).desired.values()]
    for hit in retrieval["hits"]:
        hit["payload"]["area_ids"] = [str(uid(90))]
    monkeypatch.setattr(service, "request_area", AsyncMock(return_value=None))
    union = AsyncMock(
        return_value=ResolvedResearchAreas((uid(90), uid(91)), b"synthetic-area-union")
    )
    monkeypatch.setattr(service, "request_areas", union)
    area_params = (
        []
        if area_mode == "none"
        else (
            [("area_id", str(uid(90)))]
            if area_mode == "single"
            else [
                ("area_ids", str(uid(90))),
                ("area_ids", str(uid(91))),
                ("area_ids", str(uid(90))),
            ]
        )
    )
    response = await client.get(
        PATH,
        headers=headers,
        params=area_params
        + [
            ("q", "music"),
            ("genre_keys", "1:2"),
            ("genre_keys", "2:2"),
            ("genre_keys", "1:2"),
            ("category", "2"),
        ],
    )
    assert response.status_code == 200
    request = retrieval["requests"][-1]
    assert request.url.path == "/collections/kulturbytes_events_jina_v3_v1/points/query"
    clauses = [{"key": "genre_keys", "match": {"any": ["1:2", "2:2"]}}]
    if area_mode != "none":
        clauses.insert(
            0,
            {
                "key": "area_ids",
                "match": (
                    {"any": [str(uid(90))]}
                    if area_mode == "single"
                    else {"any": [str(uid(90)), str(uid(91))]}
                ),
            },
        )
    assert json.loads(request.content)["filter"] == {"must": clauses}
    if area_mode == "multiple":
        assert union.call_args.args[1] == [uid(90), uid(91)]
        assert retrieval["rehydrate"].call_args.args[-1] == union.return_value
    filters = retrieval["rehydrate"].call_args.args[2]
    assert filters.genre_keys == ["1:2", "2:2"] and filters.category == 2
    assert retrieval["rehydrate"].call_args.args[3] == [uid(30)]


@pytest.mark.parametrize(
    "query",
    [
        "genre_keys=Jazz",
        "genre_keys=1:0",
        "genre_keys=1:2&entity_type=venue",
        "&".join(["genre_keys=1:2"] * 51),
    ],
)
async def test_api_rejects_invalid_genres_before_retrieval(client, headers, retrieval, query):
    assert (await client.get(PATH + "?q=music&" + query, headers=headers)).status_code == 422
    assert not retrieval["requests"]


@pytest.mark.integration
async def test_source_area_union_and_genre_and_category(
    admin_store, db_connection, settings, monkeypatch
):
    from contextlib import asynccontextmanager

    from fastapi import Request

    from app.errors import APIError
    from app.repositories import research_areas
    from tests.test_semantic_knowledge_index import insert_area

    @asynccontextmanager
    async def connect(request):
        yield db_connection

    monkeypatch.setattr(research_areas, "connect_admin", connect)
    request = Request({"type": "http"})
    flensburg, husum = uuid4(), uuid4()
    await insert_area(
        db_connection, flensburg, "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 921
    )
    await insert_area(db_connection, husum, "Husum", "POLYGON((8 54,9 54,9 55,8 55,8 54))", 922)
    await db_connection.execute(
        text("""UPDATE uranus.venue SET
        point=ST_SetSRID(ST_Point(CASE WHEN uuid=:a THEN 9.5 ELSE 8.5 END,54.5),4326)
        WHERE uuid=ANY(:ids)"""),
        {"a": uid(20), "ids": [uid(20), uid(21)]},
    )
    await db_connection.execute(
        text("""UPDATE uranus.event_date SET
        venue_uuid=CASE WHEN event_uuid=:a THEN CAST(:va AS uuid) ELSE CAST(:vb AS uuid) END,
        space_uuid=NULL WHERE event_uuid=ANY(:ids)"""),
        {"a": uid(30), "va": uid(20), "vb": uid(21), "ids": [uid(30), uid(32)]},
    )
    await db_connection.execute(
        text("UPDATE uranus.event SET categories=ARRAY[7] WHERE uuid=:id"), {"id": uid(30)}
    )
    await db_connection.execute(
        text("""INSERT INTO uranus.event_type_link(event_uuid,type_id,genre_id)
        VALUES (:a,1,2),(:b,1,3)"""),
        {"a": uid(30), "b": uid(32)},
    )
    union = await research_areas.request_areas(request, [flensburg, husum])
    for keys, category, expected in (
        (["1:2"], None, [uid(30)]),
        (["1:2", "1:3"], None, [uid(32), uid(30)]),
        (["1:2", "1:3"], 7, [uid(30)]),
        (["1:2"], 8, []),
    ):
        page = await rehydrate_semantic_events(
            db_connection,
            settings,
            SemanticResearchFilters(
                q="music", area_ids=[flensburg, husum], genre_keys=keys, category=category
            ),
            [uid(32), uid(30)],
            datetime.now(UTC),
            area=union,
        )
        assert [i.entity_key for i in page.items] == expected
    with pytest.raises(APIError, match="Research area was not found"):
        await research_areas.request_areas(request, [flensburg, uuid4()])
    with pytest.raises(APIError, match="must be resolved"):
        await rehydrate_semantic_events(
            db_connection,
            settings,
            SemanticResearchFilters(q="music", area_ids=[flensburg]),
            [],
            datetime.now(UTC),
        )


async def test_structured_filters_require_direct_configuration(
    client, headers, retrieval, settings
):
    settings.semantic_search_url = "https://search.example.test/search"
    settings.qdrant_url = None
    response = await client.get(PATH, headers=headers, params={"q": "music", "genre_keys": "1:2"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    assert not retrieval["requests"]
    retrieval["rehydrate"].assert_not_awaited()


def test_genre_payload_names_are_public_and_keys_are_not_embedded():
    doc = sample("event", genre_keys=["123:456"], genre_names=["Jazz private@example.test"])
    assert doc.payload.genre_names == ["Jazz"]
    assert "private@example.test" not in doc.model_dump_json()
    assert "Genres: Jazz" in doc.sections[0].text
    assert "123:456" not in doc.sections[0].text


async def test_combined_area_genre_search_rejects_outside_provider_evidence(
    client, headers, retrieval, monkeypatch
):
    areas = [uid(90), uid(91)]
    retrieval["hits"] = []
    for entity_id, memberships in ((uid(30), [uid(91)]), (uid(32), [uid(92)])):
        doc = sample("event", entity_id=entity_id, genre_keys=["1:2"], genre_names=["Jazz"])
        for _, payload in plan(doc).desired.values():
            payload["area_ids"] = [str(area) for area in memberships]
            retrieval["hits"].append({"score": 0.9, "payload": payload})
    monkeypatch.setattr(
        service,
        "request_areas",
        AsyncMock(return_value=ResolvedResearchAreas(tuple(areas), b"synthetic-area-union")),
    )
    response = await client.get(
        PATH,
        headers=headers,
        params={
            "q": "music",
            "area_ids": [str(area) for area in areas],
            "genre_keys": ["1:2"],
        },
    )
    assert response.status_code == 200
    assert retrieval["rehydrate"].call_args.args[3] == [uid(30)]
