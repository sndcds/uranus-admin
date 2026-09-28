"""Online retrieval uses fake internal HTTP, never downloads models or writes source data."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import research as research_api
from app.auth.dependencies import get_identity
from app.auth.service import AdminPrincipal
from app.database import get_connection
from app.errors import APIError
from app.logging import JsonFormatter
from app.repositories import research_areas
from app.repositories.research import rehydrate_semantic_events, research_sql
from app.research.vector_documents import DOCUMENT_VERSION
from app.research.vector_models import MODELS
from app.research.vector_sync import deduplicate
from app.research.vector_transport import Encoder, Qdrant
from app.schemas.research import ResearchPage, ResearchRecord, SemanticResearchFilters
from app.services import semantic_search as service
from tests.conftest import uid

PATH = "/api/v1/research/semantic-search"


def hit(key, score=0.8):
    return {
        "score": score,
        "payload": {
            "entity_id": str(uid(key)),
            "entity_type": "event",
            "index_owner": "uranus-admin-event-pilot-v1",
            "embedding_version": MODELS["jina-v3"].version,
            "document_schema_version": DOCUMENT_VERSION,
        },
    }


@pytest.fixture
def retrieval(settings, monkeypatch):
    settings.semantic_search_noncommercial_jina = True
    settings.qdrant_url = "http://127.0.0.1:6333"
    settings.embedding_url = "http://127.0.0.1:8090"
    from pydantic import SecretStr

    settings.qdrant_api_key = SecretStr("qdrant-test-secret")
    settings.embedding_api_key = SecretStr("encoder-test-secret")
    state = {"hits": [hit(30)], "failure": None, "requests": []}

    def respond(request):
        state["requests"].append(request)
        stage = "encoder" if request.url.path == "/embed" else "qdrant"
        if state["failure"] == stage:
            return httpx.Response(500, text="provider-secret http://private.invalid")
        if state["failure"] == stage + "-timeout":
            raise httpx.ReadTimeout("provider-secret", request=request)
        if stage == "encoder":
            return httpx.Response(
                200,
                json={
                    "embedding_version": MODELS["jina-v3"].version,
                    "vectors": [[1.0] * 1024],
                },
            )
        return httpx.Response(200, json={"result": {"points": state["hits"]}})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(service, "Encoder", lambda s, m: Encoder(s, m, transport))
    monkeypatch.setattr(service, "Qdrant", lambda s, m: Qdrant(s, m, transport))

    async def connection(request: Request):
        yield object()

    monkeypatch.setattr(service, "get_connection", connection)
    page = ResearchPage(
        items=[ResearchRecord(entity_type="event", entity_key=uid(30), name="Current")],
        pagination={"page": 1, "page_size": 20, "pages": 1, "total": 1},
        observed_at=datetime.now(UTC),
        timezone="Europe/Berlin",
    )
    state["rehydrate"] = AsyncMock(return_value=page)
    monkeypatch.setattr(service, "rehydrate_semantic_events", state["rehydrate"])
    return state


async def test_anonymous_rejected_before_retrieval(client, retrieval):
    assert (await client.get(PATH, params={"q": "creative"})).status_code == 401
    assert not retrieval["requests"]


@pytest.mark.parametrize(
    "admin,journalist,expected", [(False, False, 403), (False, True, 200), (True, False, 200)]
)
async def test_research_authorization(client, retrieval, admin, journalist, expected):
    client._transport.app.dependency_overrides[get_identity] = lambda: AdminPrincipal(
        subject="admin:test", system_admin=admin, journalist=journalist
    )
    response = await client.get(PATH, params={"q": "creative"})
    assert response.status_code == expected
    if expected == 403:
        assert not retrieval["requests"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": " "},
        {"q": " a "},
        {"q": "x" * 121},
        {"q": "ab", "model": "e5-small"},
        {"q": "ab", "entity_type": "all"},
        {"q": "ab", "page_size": 21},
        {"q": "ab", "page": 2},
        {"q": "ab", "sort": "name"},
        {"q": "ab", "from_date": "2026-03-01", "to_date": "2026-01-01"},
    ],
)
async def test_query_validation(client, headers, retrieval, params):
    response = await client.get(PATH, headers=headers, params=params)
    assert response.status_code == 422
    assert not retrieval["requests"]


@pytest.mark.parametrize("failure", ["encoder", "qdrant", "encoder-timeout", "qdrant-timeout"])
async def test_safe_provider_failures(client, headers, retrieval, failure):
    retrieval["failure"] = failure
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    assert all(
        secret not in response.text
        for secret in ("provider-secret", "private.invalid", "test-secret")
    )
    retrieval["rehydrate"].assert_not_awaited()


@pytest.mark.parametrize(
    "setting", ["semantic_search_noncommercial_jina", "embedding_url", "qdrant_url"]
)
async def test_missing_config_or_license_fails_closed(
    client, headers, settings, retrieval, setting
):
    setattr(settings, setting, False if setting.startswith("semantic") else None)
    assert (await client.get(PATH, headers=headers, params={"q": "creative"})).status_code == 503
    assert not retrieval["requests"]


async def test_unconfigured_area_storage_error_is_preserved(client, headers, retrieval, caplog):
    retrieval["hits"] = [hit(30, 0.7), hit(32, 0.9), hit(30, 0.8)]
    with caplog.at_level("INFO", logger="admin.research"):
        response = await client.get(
            PATH,
            headers=headers,
            params={
                "q": "creative private query",
                "city": "Flensburg",
                "category": 2,
                "organization_id": str(uid(10)),
                "venue_id": str(uid(20)),
                "status": "released",
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
                "area_id": str(uid(99)),
            },
        )
    # No admin engine is configured: this is a storage error, not an unknown area.
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "admin_storage_unconfigured"


@pytest.fixture(params=["vector", "gateway", "classic"])
def area_search(request, client, settings, retrieval, monkeypatch):
    """Exercise the real area resolver with a bounded synthetic admin result."""
    result = Mock()
    result.mappings.return_value.first.return_value = None
    admin = AsyncMock()
    admin.execute.return_value = result

    @asynccontextmanager
    async def connect(request):
        yield admin

    monkeypatch.setattr(research_areas, "connect_admin", connect)
    if request.param == "gateway":
        settings.semantic_search_url = "https://search.example.test/search"
        monkeypatch.setattr(service, "retrieve_candidates", AsyncMock(return_value=[]))
    elif request.param == "classic":
        client._transport.app.dependency_overrides[get_connection] = service.get_connection
        monkeypatch.setattr(research_api, "research_page", retrieval["rehydrate"])
    return ("/api/v1/research/search" if request.param == "classic" else PATH), result


async def test_unknown_area_returns_not_found(client, headers, retrieval, area_search):
    path, _ = area_search
    retrieval["hits"] = []  # An empty candidate set must not bypass area validation.
    response = await client.get(
        path, headers=headers, params={"q": "creative", "area_id": str(uid(99))}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "research_area_not_found"
    retrieval["rehydrate"].assert_not_awaited()


async def test_known_area_without_matches_returns_empty_page(
    client, headers, retrieval, area_search
):
    path, result = area_search
    result.mappings.return_value.first.return_value = {
        "id": uid(99),
        "area_type": "municipality",
        "country_code": "DE",
        "region_code": "DE-SH",
        "name": "Fixture",
        "display_name": "Fixture",
        "osm_type": "R",
        "osm_id": "876544",
        "osm_admin_level": 8,
        "centroid": {"longitude": 9.5, "latitude": 54.5},
        "bbox": (9, 54, 10, 55),
        "source": "osm",
        "retrieved_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "ewkb": b"synthetic-boundary",
    }
    retrieval["rehydrate"].return_value = ResearchPage(
        items=[],
        pagination={"page": 1, "page_size": 20, "pages": 0, "total": 0},
        observed_at=datetime.now(UTC),
        timezone="Europe/Berlin",
    )
    response = await client.get(
        path, headers=headers, params={"q": "creative", "area_id": str(uid(99))}
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 0
    assert retrieval["rehydrate"].call_args.args[-1].area.id == uid(99)


@pytest.mark.parametrize(
    "stage", ["retrieve_candidates", "request_area", "rehydrate_semantic_events"]
)
@pytest.mark.parametrize("status,code", [(403, "forbidden"), (503, "admin_storage_unconfigured")])
async def test_existing_api_errors_keep_status_code_and_message(
    client, headers, settings, retrieval, monkeypatch, stage, status, code
):
    if stage == "retrieve_candidates":
        settings.semantic_search_url = "https://search.example.test/search"
    error = APIError(status, code, "Original safe message.")
    monkeypatch.setattr(service, stage, AsyncMock(side_effect=error))
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == status
    assert response.json()["error"] == {"code": code, "message": error.message}


@pytest.mark.parametrize(
    "error,status,code",
    [
        (SQLAlchemyError("private source details"), 503, "database_unavailable"),
        (TimeoutError("private source details"), 503, "database_unavailable"),
        (ValueError("private source details"), 500, "internal_error"),
    ],
)
async def test_source_failures_are_not_semantic_provider_failures(
    client, headers, retrieval, error, status, code
):
    retrieval["rehydrate"].side_effect = error
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "private source details" not in response.text


async def test_ranked_candidates_contract_and_logs(client, headers, retrieval, monkeypatch, caplog):
    retrieval["hits"] = [hit(30, 0.7), hit(32, 0.9), hit(30, 0.8)]
    monkeypatch.setattr(service, "request_area", AsyncMock(return_value=None))
    with caplog.at_level("INFO", logger="admin.research"):
        response = await client.get(
            PATH, headers=headers, params={"q": "private query", "category": 2}
        )
    assert response.status_code == 200
    ResearchPage.model_validate(response.json())
    args = retrieval["rehydrate"].call_args.args
    assert args[2].category == 2 and args[3] == [uid(32), uid(30)]
    requests = retrieval["requests"]
    assert json.loads(requests[0].content) == {
        "model": "jina-v3",
        "kind": "query",
        "texts": ["private query"],
    }
    assert requests[1].url.path == "/collections/uranus_bench_events_jina_v3/points/query"
    assert json.loads(requests[1].content)["limit"] == 50
    logged = json.loads(
        JsonFormatter().format(
            next(r for r in caplog.records if r.message == "research_semantic_search")
        )
    )
    assert logged["candidate_count"] == 2 and logged["returned_count"] == 1
    for key in ("embedding_ms", "qdrant_ms", "postgres_rehydrate_ms", "total_ms"):
        assert logged[key] >= 0
    assert "private query" not in json.dumps(logged)
    assert "score" not in response.text


def test_dedup_keeps_candidates_beyond_first_ten():
    hits = [hit(i, i / 100) for i in range(30, 60)] + [hit(30, 0.99)]
    ranked = deduplicate(hits, {str(uid(i)) for i in range(30, 60)}, MODELS["jina-v3"], limit=50)
    assert len(ranked) == 30 and ranked[0]["payload"]["entity_id"] == str(uid(30))
    assert len(deduplicate(hits, {str(uid(i)) for i in range(30, 60)}, MODELS["jina-v3"])) == 10


async def test_rehydration_public_deleted_private_rank_and_current_data(db_connection, settings):
    await db_connection.execute(
        text("UPDATE uranus.event SET description='Current description' WHERE uuid=:id"),
        {"id": uid(30)},
    )
    filters = SemanticResearchFilters(q="not literal title")
    result = await rehydrate_semantic_events(
        db_connection,
        settings,
        filters,
        [uid(31), uid(999999), uid(32), uid(30)],
        datetime.now(UTC),
    )
    assert [i.entity_key for i in result.items] == [uid(32), uid(30)]
    assert result.items[1].description == "Current description"
    await db_connection.execute(
        text("UPDATE uranus.event_date SET release_status='draft' WHERE event_uuid=:id"),
        {"id": uid(32)},
    )
    result = await rehydrate_semantic_events(
        db_connection, settings, filters, [uid(32)], datetime.now(UTC)
    )
    assert not result.items


@pytest.mark.parametrize(
    "filters",
    [
        {"city": "Missing"},
        {"category": 2147483647},
        {"status": "deferred"},
        {"organization_id": uid(11)},
        {"venue_id": uid(22)},
        {"from_date": date(1900, 1, 1), "to_date": date(1900, 1, 2)},
    ],
)
async def test_structured_filters_remove_candidates(db_connection, settings, filters):
    result = await rehydrate_semantic_events(
        db_connection,
        settings,
        SemanticResearchFilters(q="creative", **filters),
        [uid(30), uid(32)],
        datetime.now(UTC),
    )
    assert result.items == []


def test_rehydration_is_select_only_and_candidates_are_bound():
    # Repository issues a SELECT with bound UUID arrays; no dynamic input identifiers.
    sql = research_sql(candidates=True)
    assert ":candidate_ids" in sql
    assert not any(
        word in sql.upper().split() for word in ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE")
    )


@pytest.mark.parametrize("stage", ["embedding", "rehydration"])
async def test_overall_deadline_fails_closed(client, headers, retrieval, monkeypatch, stage):
    import asyncio

    async def pending_embedding(*args, **kwargs):
        await asyncio.sleep(1)

    if stage == "embedding":
        monkeypatch.setattr(Encoder, "embed", pending_embedding)
    else:
        retrieval["rehydrate"].side_effect = pending_embedding
    monkeypatch.setattr(service, "REQUEST_TIMEOUT_SECONDS", 0.01)
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    if stage == "embedding":
        retrieval["rehydrate"].assert_not_awaited()
    else:
        retrieval["rehydrate"].assert_awaited_once()


@pytest.mark.parametrize(
    "hits",
    [
        [hit(30)] * 51,
        [
            {
                "score": 0.8,
                "payload": {
                    "entity_type": "event",
                    "index_owner": "uranus-admin-event-pilot-v1",
                    "entity_id": "bad",
                },
            }
        ],
    ],
)
async def test_malformed_response_rejected(client, headers, retrieval, hits):
    retrieval["hits"] = hits
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    retrieval["rehydrate"].assert_not_awaited()


async def test_rehydration_bound_and_read_only_transaction(db_connection, settings):
    await db_connection.execute(
        text("""INSERT INTO uranus.event
        (uuid,org_uuid,title,release_status)
        SELECT CAST('10000000-0000-0000-0000-'||lpad(n::text,12,'0') AS uuid),:org,
            'Bounded fixture','released' FROM generate_series(1,30) n"""),
        {"org": uid(10)},
    )
    from uuid import UUID

    candidates = [UUID(f"10000000-0000-0000-0000-{n:012}") for n in range(30, 0, -1)]
    page = await rehydrate_semantic_events(
        db_connection,
        settings,
        SemanticResearchFilters(q="creative"),
        candidates,
        datetime.now(UTC),
    )
    assert len(page.items) == 20
    assert [i.entity_key for i in page.items] == candidates[:20]
    assert page.pagination.total == 20 and page.pagination.pages == 1


async def test_rehydration_runs_in_read_only_transaction(db_connection, settings):
    await db_connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    page = await rehydrate_semantic_events(
        db_connection, settings, SemanticResearchFilters(q="creative"), [uid(30)], datetime.now(UTC)
    )
    assert len(page.items) == 1


@pytest.mark.parametrize("longitude,expected", [(9.5, True), (10, True), (11, False)])
async def test_semantic_area_filter_uses_current_occurrence(
    admin_store, db_connection, settings, longitude, expected
):
    from app.repositories.research_areas import resolve_area

    await db_connection.execute(
        text("""INSERT INTO admin.research_area
      (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,osm_admin_level,
       geometry,centroid,source,retrieved_at,created_at,updated_at)
      VALUES (:id,'municipality','DE','DE-SH','Fixture','Fixture','R',876544,8,
       ST_Multi(ST_GeomFromText('POLYGON((9 54,10 54,10 55,9 55,9 54))',4326)),
       ST_SetSRID(ST_Point(9.5,54.5),4326),'osm',now(),now(),now())"""),
        {"id": uid(991)},
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.venue SET point=ST_SetSRID(ST_Point(:lon,54.5),4326) "
            "WHERE uuid IN (:a,:b)"
        ),
        {"lon": longitude, "a": uid(20), "b": uid(21)},
    )
    area = await resolve_area(db_connection, uid(991))
    page = await rehydrate_semantic_events(
        db_connection,
        settings,
        SemanticResearchFilters(q="creative", area_id=uid(991)),
        [uid(30)],
        datetime.now(UTC),
        area,
    )
    assert bool(page.items) is expected


async def test_rehydrate_empty_candidates_and_page_size(db_connection, settings):
    for ids, size, expected in [([], 20, []), ([uid(32), uid(30)], 1, [uid(32)])]:
        result = await rehydrate_semantic_events(
            db_connection,
            settings,
            SemanticResearchFilters(q="creative", page_size=size),
            ids,
            datetime.now(UTC),
        )
        assert [item.entity_key for item in result.items] == expected


async def test_foreign_and_obsolete_chunks_cannot_influence_ranking(client, headers, retrieval):
    foreign = hit(30, 1)
    foreign["payload"]["index_owner"] = "foreign"
    obsolete = hit(33, 1)
    obsolete["payload"]["embedding_version"] = "old"
    retrieval["hits"] = [hit(32, 0.9), hit(30, 0.7), foreign, obsolete]
    assert (await client.get(PATH, headers=headers, params={"q": "creative"})).status_code == 200
    assert retrieval["rehydrate"].call_args.args[3] == [uid(32), uid(30)]
