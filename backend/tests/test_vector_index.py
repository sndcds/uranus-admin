"""No model downloads or network in unit tests; fixtures are synthetic public records."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

from app.config import Settings
from app.errors import APIError
from app.repositories.vector_events import extract_events
from app.research.vector_benchmark import csv_cell, quality_metrics
from app.research.vector_documents import Section, chunk_sections, clean, content_hash, document
from app.research.vector_index import SOURCE_BOUNDARY
from app.research.vector_models import MODELS
from app.research.vector_sync import apply_changes, deduplicate, plan_changes
from app.research.vector_transport import Encoder, InternalHTTP, Qdrant, validate_vectors


def sample(**changes):
    row = {
        "entity_id": uuid4(),
        "organization_id": uuid4(),
        "title": "Sprachkurs",
        "status": "released",
        "description": "<p>Dänisch lernen</p>",
        **changes,
    }
    return document(row, {"venue_names": ["VHS"], "area_names": ["Flensburg"]})


def prepare(doc):
    return {
        str(doc.entity_id): chunk_sections(
            doc.sections, lambda s: len(s.split()) + 2, prefix="passage: "
        )
    }


def test_public_allowlist_and_normalization():
    doc = sample(
        admin_note="INTERNAL",
        registration_email="private@example.test",
        password="PASSWORD",
        description="<script>SECRET</script> Hallo a@example.test",
        price_type="free",
        ticket_flags=["registration_required"],
        language="de",
    )
    value = "\n".join(s.text for s in doc.sections)
    assert "kostenlos" in value and "Anmeldung erforderlich" in value and "Flensburg" in value
    assert all(v not in value for v in ("INTERNAL", "PASSWORD", "SECRET", "@", str(doc.entity_id)))
    assert not any(k in doc.payload for k in ("description", "title", "registration_email"))
    assert clean("  e\u0301 <b>Hallo</b>  ") == "é Hallo"
    assert not clean("https://example.test/?token=secret")


def test_empty_fields_hash_stability_and_relevant_change():
    doc = sample(description=None, subtitle="", source_updated_at=datetime.now(UTC))
    assert len(doc.sections) == 1 and "None" not in doc.sections[0].text
    chunks = prepare(doc)
    assert len(chunks[str(doc.entity_id)]) == 1
    changed = doc.model_copy(deep=True)
    changed.payload["source_updated_at"] = "different"
    assert prepare(changed) == chunks
    changed.sections[0].text += " geändert"
    assert prepare(changed) != chunks
    assert content_hash("ä") == content_hash("ä") != content_hash("a")


def test_chunk_limit_overlap_semantic_sections_and_exact_hash():
    prose = " ".join(f"Wort{i}." for i in range(1400))
    chunks = chunk_sections(
        [
            Section(kind="content", text=prose),
            Section(kind="tickets", text="Anmeldung erforderlich."),
        ],
        lambda s: len(s.split()) + 2,
        prefix="passage: ",
    )
    assert len(chunks) > 3 and chunks[-1].chunk_kind == "tickets"
    assert all(c.token_count <= 480 and c.content_hash == content_hash(c.text) for c in chunks)
    assert all(f"Wort{i}." in " ".join(c.text for c in chunks) for i in range(1400))
    assert set(chunks[0].text.split()[-40:]) & set(chunks[1].text.split()[1:80])


def test_chunk_character_boundaries_and_identical_sections_dedup():
    sections = [Section(kind="content", text="あ" * 1500)] * 2
    chunks = chunk_sections(sections, len)
    assert all(len(c.text) <= 480 for c in chunks)
    assert len({(c.chunk_kind, c.content_hash) for c in chunks}) == len(chunks)


def test_incremental_metadata_version_and_stale_reconciliation():
    doc = sample()
    chunks = prepare(doc)
    model = MODELS["e5-small"]
    first = plan_changes([doc], chunks, {}, model, complete=True)
    assert first.new == 1 and not first.delete
    existing = {i: p for i, (_, p) in first.desired.items()}
    assert plan_changes([doc], chunks, existing, model, complete=True).unchanged == 1
    old = next(iter(existing.values()))
    old["source_updated_at"] = "old"
    metadata = plan_changes([doc], chunks, existing, model, complete=True)
    assert len(metadata.metadata) == 1 and not metadata.embed
    old["embedding_version"] = "old"
    assert len(plan_changes([doc], chunks, existing, model, complete=True).embed) == 1
    assert plan_changes([], {}, existing, model, complete=False).delete == []
    assert len(plan_changes([], {}, existing, model, complete=True).delete) == 1
    changed = doc.model_copy(deep=True)
    changed.sections[0].text += " Changed"
    updated = plan_changes([changed], prepare(changed), existing, model, complete=False)
    assert len(updated.embed) == 1 and len(updated.delete) == 1


async def test_apply_upsert_before_delete_and_metadata_without_embedding():
    events = []

    class Store:
        async def info(self):
            return None

        async def create(self):
            events.append("create")

        async def upsert(self, points):
            events.append("upsert")

        async def payload(self, identifier, payload):
            events.append("metadata")

        async def delete(self, ids):
            events.append("delete")

    class Embed:
        metrics = []

        async def embed(self, texts):
            events.append("embed")
            return [[1.0] * 384 for _ in texts]

    doc = sample()
    plan = plan_changes([doc], prepare(doc), {}, MODELS["e5-small"], complete=True)
    await apply_changes(Store(), Embed(), plan)
    assert events == ["create", "embed", "upsert", "delete"]
    events.clear()
    plan.metadata = plan.embed
    plan.embed = []
    await apply_changes(Store(), Embed(), plan)
    assert "metadata" in events and "embed" not in events


@pytest.mark.parametrize("values", [[], [[1]], [[float("nan")] * 384], [[True] * 384], [[0] * 384]])
def test_invalid_vectors(values):
    with pytest.raises(ValueError):
        validate_vectors(values, MODELS["e5-small"], 1)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://evil.test"}),
        httpx.Response(500, text="SECRET"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, content=b"{bad", headers={"content-type": "application/json"}),
        httpx.Response(200, json=[]),
        httpx.Response(
            200, content=b"x" * (8 * 1024 * 1024 + 1), headers={"content-type": "application/json"}
        ),
    ],
)
async def test_transport_rejects_provider_response_safely(response):
    client = InternalHTTP(
        "https://internal.test",
        "secret",
        1,
        "api-key",
        httpx.MockTransport(lambda request: response),
    )
    try:
        with pytest.raises(APIError) as error:
            await client.request("GET", "/collections")
        assert "SECRET" not in str(error.value)
    finally:
        await client.close()


async def test_transport_timeout():
    def timeout(request):
        raise httpx.ReadTimeout("SECRET")

    client = InternalHTTP(
        "https://internal.test", "secret", 1, "api-key", httpx.MockTransport(timeout)
    )
    try:
        with pytest.raises(APIError):
            await client.request("GET", "/")
    finally:
        await client.close()


def vector_settings(settings):
    settings.qdrant_url = "https://internal.test"
    settings.qdrant_api_key = SecretStr("x" * 48)
    settings.embedding_url = "https://encoder.test"
    settings.embedding_api_key = SecretStr("y" * 48)
    return settings


async def test_qdrant_foreign_collection_and_bad_dimensions(settings):
    settings = vector_settings(settings)
    q = Qdrant(
        settings,
        "e5-small",
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "result": {
                        "config": {"params": {"vectors": {"size": 10, "distance": "Cosine"}}}
                    }
                },
            )
        ),
    )
    try:
        with pytest.raises(ValueError, match="incompatible"):
            await q.info()
    finally:
        await q.http.close()
    q = Qdrant(
        settings,
        "e5-small",
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"result": {"points": [{"id": str(uuid4()), "payload": {}}]}}
            )
        ),
    )
    try:
        with pytest.raises(ValueError, match="foreign"):
            await q.points()
    finally:
        await q.http.close()


async def test_encoder_invalid_version(settings):
    encoder = Encoder(
        vector_settings(settings),
        "e5-small",
        httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"embedding_version": "wrong", "vectors": [[1] * 384]}
            )
        ),
    )
    try:
        with pytest.raises(ValueError, match="version"):
            await encoder.embed(["passage: text"])
    finally:
        await encoder.http.close()


def test_deduplication_metrics_and_csv():
    model = MODELS["e5-small"]
    doc = sample()
    plan = plan_changes([doc], prepare(doc), {}, model, complete=True)
    payload = next(iter(plan.desired.values()))[1]
    hits = [{"score": 0.5, "payload": payload}, {"score": 0.9, "payload": payload}]
    assert deduplicate(hits, {str(doc.entity_id)}, model) == [hits[1]]
    assert not deduplicate(hits, set(), model)
    assert quality_metrics([{"manual_relevance": ""}]) is None
    rows = [
        {
            "query_id": "q",
            "model": "m",
            "rank": n,
            "entity_id": str(n),
            "manual_relevance": 2 if n == 2 else 0,
        }
        for n in range(1, 11)
    ]
    result = quality_metrics(rows)
    assert result["m:precision_at_5"] == 0.2 and result["m:mrr_at_10"] == 0.5
    assert csv_cell("=FORMULA()") == "'=FORMULA()"


@pytest.mark.parametrize(
    "origin",
    [
        "http://remote.test",
        "https://user:pass@host.test",
        "https://host.test/path",
        "https://host.test/?token=secret",
    ],
)
def test_vector_origin_policy(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, qdrant_url=origin, qdrant_api_key=SecretStr("x" * 48))


ENCODER_PATH = Path(__file__).resolve().parents[2] / "deploy/research-ai/encoder.py"


async def test_internal_service_auth_limits_and_no_model_download():
    path = ENCODER_PATH
    spec = importlib.util.spec_from_file_location("pilot_encoder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Runtime:
        def embed(self, body):
            return {"vectors": [[1, 2]], "embedding_version": "fixture"}

    app = module.create_app(Runtime(), "x" * 48)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        body = {"model": "e5-small", "texts": ["hello"], "kind": "query"}
        assert (await c.post("/embed", json=body)).status_code == 401
        headers = {"Authorization": "Bearer " + "x" * 48}
        assert (await c.post("/embed", json=body, headers=headers)).status_code == 200
        body["model"] = "https://evil.test/model"
        assert (await c.post("/embed", json=body, headers=headers)).status_code == 422
        assert (
            await c.post("/embed", content=b"x" * (2 * 1024 * 1024 + 1), headers=headers)
        ).status_code == 413
        assert (await c.get("/health")).status_code == 200


@pytest.mark.integration
async def test_public_extraction_and_read_only_role(db_connection, settings, now):
    documents, total = await extract_events(db_connection, None, settings, now)
    assert total == len(documents) > 0
    assert all(
        d.payload["status"] in {"released", "cancelled", "deferred", "rescheduled"}
        for d in documents
    )
    assert all(not d.payload["area_assignment_available"] for d in documents)
    assert all("registration_email" not in d.payload for d in documents)
    limited, count = await extract_events(db_connection, None, settings, now, 1)
    assert count == total and len(limited) == 1
    # Synthetic fixture connection owns the source, so the CLI must refuse it.
    assert (await db_connection.execute(text(SOURCE_BOUNDARY))).scalar_one()


@pytest.mark.integration
async def test_occurrence_context_and_public_date_gate(db_connection, settings, now):
    from tests.conftest import uid

    await db_connection.execute(
        text("UPDATE uranus.event SET space_uuid=:space WHERE uuid=:id"),
        {"space": uid(25), "id": uid(30)},
    )
    await db_connection.execute(
        text("UPDATE uranus.event_date SET venue_uuid=:venue,space_uuid=NULL WHERE event_uuid=:id"),
        {"venue": uid(21), "id": uid(30)},
    )
    documents, _ = await extract_events(db_connection, None, settings, now)
    selected = next(d for d in documents if d.entity_id == uid(30))
    assert selected.payload["venue_ids"] == [str(uid(21))]
    assert selected.payload["space_ids"] == []
    await db_connection.execute(
        text("UPDATE uranus.event_date SET release_status='draft' WHERE event_uuid=:id"),
        {"id": uid(30)},
    )
    documents, _ = await extract_events(db_connection, None, settings, now)
    assert uid(30) not in {d.entity_id for d in documents}


@pytest.mark.integration
async def test_real_qdrant_reconciliation(settings):
    import os
    from urllib.parse import urlsplit

    origin = os.environ.get("TEST_QDRANT_URL")
    if not origin:
        pytest.skip("Set TEST_QDRANT_URL for isolated Qdrant integration")
    assert urlsplit(origin).hostname in {"127.0.0.1", "localhost"}, "Only loopback test instances"
    settings = vector_settings(settings)
    settings.qdrant_url = origin
    settings.qdrant_api_key = SecretStr("vector-test-only-key-with-more-than-32-characters")
    settings.qdrant_collection_prefix = "uranus_test_" + uuid4().hex[:12]
    q = Qdrant(settings, "e5-small")

    class Embed:
        metrics = []

        async def embed(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

    doc = sample()
    try:
        assert await q.info() is None
        first = plan_changes([doc], prepare(doc), {}, MODELS["e5-small"], complete=True)
        await apply_changes(q, Embed(), first)
        points = await q.points()
        assert len(points) == 1
        assert len(await q.search([1.0] + [0.0] * 383, 10)) == 1
        unchanged = plan_changes([doc], prepare(doc), points, MODELS["e5-small"], complete=True)
        assert unchanged.unchanged == 1 and not unchanged.embed
        identifier = next(iter(points))
        bad = {**points[identifier], "embedding_version": "outdated"}
        await q.payload(identifier, bad)
        repair = plan_changes(
            [doc], prepare(doc), await q.points(), MODELS["e5-small"], complete=True
        )
        assert len(repair.embed) == 1
        await apply_changes(q, Embed(), repair)
        assert len(await q.points()) == 1
        deletion = plan_changes([], {}, await q.points(), MODELS["e5-small"], complete=True)
        await apply_changes(q, Embed(), deletion)
        assert await q.points() == {}
    finally:
        await q.http.request("DELETE", q.path, missing=True)
        await q.http.close()


def test_chunk_overlap_preserves_word_separators():
    text = " ".join(f"sentence{i}." for i in range(1000))
    chunks = chunk_sections([Section(kind="content", text=text)], lambda s: len(s.split()) + 2)
    import re

    assert not any(re.search(r"\.sentence", c.text) for c in chunks)


def test_reject_duplicate_judgment_rank_and_nonfinite_score():
    rows = [{"query_id": "q", "model": "m", "entity_id": "x", "rank": 1, "manual_relevance": 2}] * 2
    with pytest.raises(ValueError, match="ranking"):
        quality_metrics(rows)
    with pytest.raises(ValueError, match="score"):
        deduplicate([{"score": float("nan")}], set(), MODELS["e5-small"])


@pytest.mark.integration
@pytest.mark.parametrize("longitude,expected", [(9.5, True), (10, True), (11, False)])
async def test_vector_area_covers_context(admin_store, db_connection, longitude, expected):
    from app.repositories.vector_events import area_memberships

    identifier = uuid4()
    await db_connection.execute(
        text("""INSERT INTO admin.research_area
      (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,osm_admin_level,
       geometry,centroid,source,retrieved_at,created_at,updated_at)
      VALUES (:id,'municipality','DE','DE-SH','Fixture','Fixture','R',876543,8,
       ST_Multi(ST_GeomFromText('POLYGON((9 54,10 54,10 55,9 55,9 54))',4326)),
       ST_SetSRID(ST_Point(9.5,54.5),4326),'osm',now(),now(),now())"""),
        {"id": identifier},
    )
    venue_id = uuid4()
    available, areas = await area_memberships(
        db_connection, [{"venue_id": venue_id, "longitude": longitude, "latitude": 54.5}]
    )
    assert available
    assert bool(areas.get(str(venue_id))) is expected
    if expected:
        assert areas[str(venue_id)] == [{"id": str(identifier), "name": "Fixture"}]


@pytest.mark.parametrize("grade", [True, 1.5, -1, "2.1"])
def test_relevance_grades_are_not_coerced(grade):
    with pytest.raises(ValueError, match="grade"):
        quality_metrics(
            [
                {
                    "query_id": "q",
                    "model": "m",
                    "entity_id": "e",
                    "rank": 1,
                    "manual_relevance": grade,
                }
            ]
        )
