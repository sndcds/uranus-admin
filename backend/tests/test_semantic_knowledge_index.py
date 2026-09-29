"""Synthetic public data only. Never contact an encoder or production vector store."""

import json
from copy import deepcopy
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.repositories.vector_entities import extract_organizations, extract_venues
from app.repositories.vector_events import area_memberships, extract_events
from app.research.semantic_contracts import COLLECTIONS, OWNER, SemanticDocument, semantic_point_id
from app.research.semantic_documents import (
    event_document,
    organization_document,
    public_clean,
    venue_document,
)
from app.research.semantic_evidence import area_filter, semantic_hits
from app.research.vector_documents import Section, chunk_sections, content_hash
from app.research.vector_models import MODELS
from app.research.vector_sync import apply_changes, plan_changes
from app.research.vector_transport import Encoder, Qdrant
from tests.test_vector_index import vector_settings

MODEL = MODELS["jina-v3"]


def sample(entity, **changes):
    row = {
        "entity_id": uuid4(),
        "organization_id": uuid4(),
        "name": "Kulturhaus",
        "title": "Sprachkurs",
        "scope": "organization",
        "status": "released",
        "description": "Öffentliche Kultur",
        **changes,
    }
    if entity == "event":
        return event_document(row, {})
    if entity == "venue":
        return venue_document(row, [], True)
    return organization_document(row, [], [], True)


def prepare(doc):
    return {str(doc.entity_id): chunk_sections(doc.sections, lambda s: len(s.split()) + 2)}


def plan(doc, old=None, complete=True):
    return plan_changes(
        [doc], prepare(doc), old or {}, MODEL, complete=complete, entity=doc.entity_type
    )


@pytest.mark.parametrize("entity", COLLECTIONS)
def test_closed_public_documents_and_evidence(entity):
    private = "private@example.test Telefon: 04841 123456 +49 (0) 461 1234567 " + str(uuid4())
    doc = sample(
        entity,
        description="Öffentlich " + private,
        admin_note="PRIVATE_NOTE",
        contact_email="secret@example.test",
        contact_phone="PRIVATE_PHONE",
        api_import_token="TOKEN",
        registration_email="secret@example.test",
        password_hash="HASH",
        findings="FINDING",
        session="SESSION",
        users=["USER"],
        event_titles=["UNBOUNDED_EVENT_LIST"],
    )
    dumped = doc.model_dump_json()
    assert all(
        s not in dumped
        for s in (
            "@",
            "04841",
            "1234567",
            "PRIVATE_NOTE",
            "PRIVATE_PHONE",
            "TOKEN",
            "HASH",
            "SESSION",
            "FINDING",
            "UNBOUNDED_EVENT_LIST",
        )
    )
    assert doc.display_name and "Öffentlich" in dumped
    result = plan(doc)
    for chunk, payload in result.desired.values():
        assert payload["chunk_text"] == chunk.text
        assert content_hash(chunk.text) == payload["content_hash"]
        assert payload["display_name"] == doc.display_name
        assert payload["document_schema_version"] == COLLECTIONS[entity].document_version
        assert payload["index_owner"] == OWNER
    value = doc.model_dump()
    value["payload"]["private_note"] = "NO"
    with pytest.raises(ValidationError):
        SemanticDocument.model_validate(value)


@pytest.mark.parametrize(
    "raw",
    [
        "+45 12 34 56 78",
        "0049 461 123456",
        "Tel. 12345678",
        "Telefon: 04841/123456",
        "fax: +49 (0) 461 1234567",
        "tel:+494611234567",
        "mailto:private@example.test",
        "https://example.test/?token=secret",
        "https://user:pass@example.test/path",
        "https://example.test/" + str(uuid4()),
    ],
)
def test_contact_url_stripping(raw):
    assert not public_clean(raw)


def test_public_numbers_links_and_names_remain():
    raw = "Hafenstraße 3, 25813 Husum. 28.09.2026 18:30. 12–18 Jahre. 10–25 EUR."
    assert public_clean(raw) == raw
    assert public_clean("https://example.test/public") == "https://example.test/public"
    assert public_clean("<script>SECRET</script> e\u0301") == "é"


@pytest.mark.parametrize("entity", COLLECTIONS)
def test_reconciliation_all_entities(entity):
    doc = sample(entity)
    first = plan(doc)
    existing = {i: p for i, (_, p) in first.desired.items()}
    assert first.new and not first.delete
    assert plan(doc, existing).unchanged == len(existing)
    metadata = doc.model_copy(deep=True)
    metadata.payload.area_ids = [uuid4()]
    changed = plan(metadata, existing)
    assert changed.metadata and not changed.embed
    renamed = doc.model_copy(deep=True)
    renamed.sections[0].text += " Neue Beschreibung"
    changed = plan(renamed, existing, complete=False)
    assert changed.embed and changed.delete
    old = deepcopy(existing)
    for p in old.values():
        p["document_schema_version"] = "older-reviewed-schema"
    assert plan(doc, old).metadata and not plan(doc, old).embed
    for p in old.values():
        p["embedding_version"] = "old"
    assert plan(doc, old).embed
    # Deletion and loss of public eligibility both remove the document from the snapshot.
    assert not plan_changes([], {}, existing, MODEL, complete=False, entity=entity).delete
    assert plan_changes([], {}, existing, MODEL, complete=True, entity=entity).delete
    for p in old.values():
        p["index_owner"] = "foreign"
    with pytest.raises(ValueError, match="foreign"):
        plan(doc, old)
    other = next(t for t in COLLECTIONS if t != entity)
    with pytest.raises(ValueError, match="mismatch"):
        plan_changes([doc], prepare(doc), {}, MODEL, complete=True, entity=other)


def test_point_identity_includes_type():
    identity = uuid4()
    docs = [sample(entity, entity_id=identity) for entity in COLLECTIONS]
    chunk = chunk_sections([Section(kind="content", text="Same")], len)[0]
    assert len({semantic_point_id(d, chunk) for d in docs}) == 3


def test_evidence_deterministic_unique_bounded_and_allowlisted():
    doc = sample("event")
    payload = next(iter(plan(doc).desired.values()))[1]
    hits = []
    for kind, value, score in [
        ("content", "Kultur", 0.5),
        ("accessibility", "Rollstuhl", 0.9),
        ("tickets", "Frei", 0.9),
        ("tickets", "Eintritt", 0.7),
        ("additional", "Frei", 0.6),
        ("participation", "Anmeldung", 0.4),
    ]:
        hits.append(
            {
                "score": score,
                "payload": {
                    **payload,
                    "chunk_kind": kind,
                    "evidence_contexts": [{"scope": "venue", "venue_id": str(uuid4())}]
                    if kind == "accessibility"
                    else [{"scope": "event"}],
                    "chunk_text": value,
                    "content_hash": content_hash(value),
                    "internal_note": "SECRET",
                },
            }
        )
    kwargs = {"entity": "event", "supporting": 2}
    result = semantic_hits(hits, {doc.entity_id}, MODEL, **kwargs)
    assert result == semantic_hits(list(reversed(hits)), {doc.entity_id}, MODEL, **kwargs)
    assert result[0].score == 0.9
    assert result[0].winning_chunk.chunk_kind == "accessibility"
    assert len(result[0].supporting_chunks) == 2
    assert "SECRET" not in result[0].model_dump_json()
    assert not semantic_hits(hits, set(), MODEL, entity="event")
    for score in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="score"):
            semantic_hits([{"score": score}], set(), MODEL, entity="event")
    hits[0]["payload"]["chunk_text"] = "private@example.test"
    with pytest.raises(ValueError, match="unsafe"):
        semantic_hits(hits, {doc.entity_id}, MODEL, entity="event")


def test_organization_area_mode_required():
    with pytest.raises(ValueError, match="mode"):
        area_filter("organization", uuid4())
    assert (
        area_filter("organization", uuid4(), organization_mode="home")["must"][0]["key"]
        == "home_area_ids"
    )
    assert area_filter("venue", uuid4())["must"][0]["key"] == "area_ids"


@pytest.mark.parametrize("entity", COLLECTIONS)
async def test_registry_foreign_points_and_collection_guard(settings, entity):
    requests = []

    def serve(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "id": str(uuid4()),
                            "payload": {
                                "entity_type": entity,
                                "index_owner": "uranus-admin-event-pilot-v1",
                            },
                        }
                    ]
                }
            },
        )

    q = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity=entity)
    try:
        assert q.collection == COLLECTIONS[entity].name
        with pytest.raises(ValueError, match="foreign"):
            await q.points()
        other = next(t for t in COLLECTIONS if t != entity)
        with pytest.raises(ValueError, match="mismatch"):
            await apply_changes(q, None, plan(sample(other)))
        assert len(requests) == 1  # No write request on rejected plan.
    finally:
        await q.http.close()


async def test_encoder_passage_contract_and_legacy_collection(settings):
    bodies = []

    def serve(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"embedding_version": MODEL.version, "vectors": [[1.0] + [0.0] * 1023]}
        )

    encoder = Encoder(vector_settings(settings), "jina-v3", httpx.MockTransport(serve))
    q = Qdrant(settings, "jina-v3")
    try:
        await encoder.embed(["Öffentliche Passage"])
        await encoder.embed(["Suchtext"], query=True)
        assert bodies[0] == {
            "model": "jina-v3",
            "kind": "passage",
            "texts": ["Öffentliche Passage"],
        }
        assert bodies[1]["kind"] == "query"
        assert q.collection == settings.qdrant_collection_prefix + "_events_jina_v3"
    finally:
        await q.http.close()
        await encoder.http.close()


async def insert_area(connection, identity, name, polygon, osm_id):
    await connection.execute(
        text("""INSERT INTO admin.research_area
        (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,osm_admin_level,
         geometry,centroid,source,retrieved_at,created_at,updated_at)
        VALUES (:id,'municipality','DE','DE-SH',:name,:name,'R',:osm,8,
        ST_Multi(ST_GeomFromText(:polygon,4326)),ST_SetSRID(ST_Point(9,54),4326),
        'osm',now(),now(),now())"""),
        {"id": identity, "name": name, "polygon": polygon, "osm": osm_id},
    )


@pytest.mark.integration
async def test_husum_flensburg_end_to_end(admin_store, db_connection, settings, now):
    from tests.conftest import uid

    husum, flensburg = uuid4(), uuid4()
    await insert_area(db_connection, husum, "Husum", "POLYGON((8 54,9 54,9 55,8 55,8 54))", 801)
    await insert_area(
        db_connection, flensburg, "Flensburg", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 802
    )
    await db_connection.execute(
        text("""UPDATE uranus.organization SET
        name='Flensburger Veranstaltungsgesellschaft mbH',point=ST_SetSRID(ST_Point(9.5,54.5),4326)
        WHERE uuid=:id"""),
        {"id": uid(10)},
    )
    await db_connection.execute(
        text("""UPDATE uranus.venue SET
        point=ST_SetSRID(ST_Point(CASE WHEN uuid=:husum THEN 8.5 ELSE 9.5 END,54.5),4326),
        accessibility_summary='Barrierefreier Eingang' WHERE uuid=ANY(:ids)"""),
        {"husum": uid(20), "ids": [uid(20), uid(21)]},
    )
    await db_connection.execute(
        text("""UPDATE uranus.event_date SET
        venue_uuid=CASE WHEN event_uuid=:husum THEN CAST(:hvenue AS uuid)
        ELSE CAST(:fvenue AS uuid) END,space_uuid=NULL
        WHERE event_uuid=ANY(:ids)"""),
        {"husum": uid(30), "hvenue": uid(20), "fvenue": uid(21), "ids": [uid(30), uid(32)]},
    )
    docs, _ = await extract_events(db_connection, db_connection, settings, now, semantic=True)
    a, b = (next(d for d in docs if d.entity_id == uid(i)) for i in (30, 32))
    assert a.payload.area_ids == [husum] and b.payload.area_ids == [flensburg]
    assert a.payload.effective_venue_id == uid(20) and a.payload.effective_longitude == 8.5
    assert a.payload.effective_space_id is None
    hits = [{"score": 0.9, "payload": next(iter(plan(d).desired.values()))[1]} for d in (a, b)]
    assert [
        h.entity_id
        for h in semantic_hits(
            hits, {a.entity_id, b.entity_id}, MODEL, entity="event", area_id=husum
        )
    ] == [a.entity_id]
    venues, _ = await extract_venues(db_connection, db_connection, settings, now)
    venue = next(d for d in venues if d.entity_id == uid(20))
    assert venue.payload.area_ids == [husum]
    venue_hits = [{"score": 0.8, "payload": next(iter(plan(venue).desired.values()))[1]}]
    assert semantic_hits(venue_hits, {venue.entity_id}, MODEL, entity="venue", area_id=husum)
    assert any(s.kind == "accessibility" for s in venue.sections)
    orgs, _ = await extract_organizations(db_connection, db_connection, settings, now)
    org = next(d for d in orgs if d.entity_id == uid(10))
    assert org.payload.home_area_ids == [flensburg]
    assert husum in org.payload.activity_area_ids and husum not in org.payload.home_area_ids
    assert org.payload.area_ids == []  # No ambiguous alias for organization geography.
    org_hits = [{"score": 0.8, "payload": next(iter(plan(org).desired.values()))[1]}]
    assert semantic_hits(
        org_hits,
        {org.entity_id},
        MODEL,
        entity="organization",
        area_id=husum,
        organization_mode="activity",
    )
    assert not semantic_hits(
        org_hits,
        {org.entity_id},
        MODEL,
        entity="organization",
        area_id=husum,
        organization_mode="home",
    )
    # No-longer-public entities are absent, so a complete reconcile removes old points.
    await db_connection.execute(
        text("UPDATE uranus.event SET release_status='draft' WHERE org_uuid=:id"), {"id": uid(10)}
    )
    assert not (await extract_events(db_connection, db_connection, settings, now, semantic=True))[0]
    assert not (await extract_organizations(db_connection, db_connection, settings, now))[0]


@pytest.mark.integration
async def test_missing_points_and_invalid_overlap(admin_store, db_connection, settings, now):
    docs, _ = await extract_venues(db_connection, db_connection, settings, now)
    from tests.conftest import uid

    venue = next(d for d in docs if d.entity_id == uid(20))
    assert venue.payload.latitude is None and venue.payload.area_ids == []
    polygon = "POLYGON((8 54,9 54,9 55,8 55,8 54))"
    await insert_area(db_connection, uuid4(), "A", polygon, 811)
    await insert_area(db_connection, uuid4(), "B", "POLYGON((9 54,10 54,10 55,9 55,9 54))", 812)
    boundary_point = uuid4()
    available, memberships = await area_memberships(
        db_connection, [{"venue_id": boundary_point, "longitude": 9, "latitude": 54.5}]
    )
    assert available and {a["name"] for a in memberships[str(boundary_point)]} == {"A", "B"}
    await insert_area(db_connection, uuid4(), "Invalid overlap", polygon, 813)
    with pytest.raises(ValueError, match="overlapping"):
        await area_memberships(
            db_connection, [{"venue_id": uuid4(), "longitude": 8.5, "latitude": 54.5}]
        )


@pytest.mark.parametrize("entity", COLLECTIONS)
@pytest.mark.parametrize("diagnostic_limit", [None, 5])
async def test_plan_closes_all_connections_before_network_and_never_embeds(
    monkeypatch, settings, entity, diagnostic_limit
):
    import argparse
    from contextlib import asynccontextmanager

    from app.research import vector_index

    lifecycle = []
    document = sample(entity)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

    class Connection:
        @asynccontextmanager
        async def begin(self):
            yield

        async def execute(self, sql):
            assert "network" not in lifecycle
            return Result(False if str(sql) == vector_index.SOURCE_BOUNDARY else 1)

    class Engine:
        def __init__(self, name):
            self.name = name

        @asynccontextmanager
        async def connect(self):
            lifecycle.append(self.name + "_open")
            yield Connection()
            lifecycle.append(self.name + "_closed")

        async def dispose(self):
            lifecycle.append(self.name + "_disposed")

    async def extract(*args, **kwargs):
        return [document], 1

    async def boundary(*args):
        pass

    def network():
        assert all(
            key in lifecycle
            for key in ("source_closed", "admin_closed", "source_disposed", "admin_disposed")
        )
        lifecycle.append("network")

    class HTTP:
        async def close(self):
            pass

    class EncoderStub:
        http = HTTP()

        def __init__(self, *args):
            network()

        async def prepare(self, documents):
            return prepare(document)

        async def embed(self, *args):
            pytest.fail("plan must never embed")

    class Store:
        http = HTTP()
        collection = COLLECTIONS[entity].name

        def __init__(self, *args, **kwargs):
            network()

        async def info(self):
            return {"points_count": 1} if diagnostic_limit else None

        async def points(self):
            return {
                i: {**p, "source_updated_at": "older"}
                for i, (_, p) in plan(document).desired.items()
            }

        async def create(self):
            pytest.fail("plan must never create a collection")

    monkeypatch.setattr(vector_index, "create_engine", lambda settings: Engine("source"))
    monkeypatch.setattr(vector_index, "create_admin_engine", lambda settings: Engine("admin"))
    monkeypatch.setattr(vector_index, "assert_admin_boundary", boundary)
    monkeypatch.setattr(vector_index, "extract_events", extract)
    monkeypatch.setattr(vector_index, "extract_venues", extract)
    monkeypatch.setattr(vector_index, "extract_organizations", extract)
    monkeypatch.setattr(vector_index, "Encoder", EncoderStub)
    monkeypatch.setattr(vector_index, "Qdrant", Store)
    result = await vector_index.run(
        argparse.Namespace(
            entity=entity,
            command="plan",
            model="jina-v3",
            limit=None,
            output=None,
            metadata_diagnostics=diagnostic_limit,
        ),
        settings,
    )
    assert (
        result["source_entity_count"]
        == result["selected_public_count"]
        == result["document_count"]
        == 1
    )
    assert result["approximate_payload_bytes"] > 0
    if diagnostic_limit:
        assert result["metadata_diagnostics"][0]["fields"][0]["field"] == "source_updated_at"


@pytest.mark.parametrize("entity", COLLECTIONS)
def test_actual_multisection_evidence_and_chunk_provenance(entity):
    doc = sample(
        entity, source_link="https://example.test/public", web_link="https://example.test/public"
    )
    prepared = prepare(doc)
    payload = next(iter(plan(doc).desired.values()))[1]
    result = semantic_hits(
        [{"score": 0.7, "payload": payload}], {doc.entity_id}, MODEL, entity=entity
    )
    assert result[0].winning_chunk.chunk_text == prepared[str(doc.entity_id)][0].text
    wrong = prepared[str(doc.entity_id)][0].model_copy(
        update={"text": "Unrelated text", "content_hash": content_hash("Unrelated text")}
    )
    with pytest.raises(ValueError, match="unmatched"):
        plan_changes([doc], {str(doc.entity_id): [wrong]}, {}, MODEL, complete=True, entity=entity)


@pytest.mark.integration
async def test_venue_loses_public_eligibility_and_partial_limit(
    admin_store, db_connection, settings, now
):
    from tests.conftest import uid

    documents, total = await extract_venues(db_connection, db_connection, settings, now)
    limited, count = await extract_venues(db_connection, db_connection, settings, now, 1)
    assert len(limited) == 1 and count == total == len(documents)
    old = next(d for d in documents if d.entity_id == uid(20))
    existing = {i: p for i, (_, p) in plan(old).desired.items()}
    await db_connection.execute(text("UPDATE uranus.event SET release_status='draft'"))
    remaining, _ = await extract_venues(db_connection, db_connection, settings, now)
    assert not remaining
    assert plan_changes(remaining, {}, existing, MODEL, complete=True, entity="venue").delete
    assert not plan_changes(remaining, {}, existing, MODEL, complete=False, entity="venue").delete


@pytest.mark.parametrize(
    "entity,mode,key",
    [
        ("event", None, "area_ids"),
        ("venue", None, "area_ids"),
        ("organization", "home", "home_area_ids"),
        ("organization", "activity", "activity_area_ids"),
    ],
)
async def test_geography_filter_sent_before_vector_ranking(settings, entity, mode, key):
    requests = []
    area = uuid4()

    def serve(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"result": {"points": []}})

    q = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity=entity)
    try:
        await q.search([1.0] + [0.0] * 1023, 10, area_id=area, organization_mode=mode)
        assert requests[0]["filter"] == {"must": [{"key": key, "match": {"any": [str(area)]}}]}
    finally:
        await q.http.close()


@pytest.mark.parametrize(
    "entity,mode,key",
    [
        ("event", None, "area_ids"),
        ("venue", None, "area_ids"),
        ("organization", "home", "home_area_ids"),
        ("organization", "activity", "activity_area_ids"),
    ],
)
@pytest.mark.parametrize(
    "selection", ["single", "one_item", "multiple", "duplicates", "no_matches"]
)
async def test_synthetic_multi_area_transport_and_evidence(settings, entity, mode, key, selection):
    """Synthetic Qdrant boundary: apply its wire filter before ranking/limiting."""
    flensburg, aabenraa, sonderborg, husum, elsewhere = [uuid4() for _ in range(5)]
    memberships = [[flensburg], [aabenraa], [sonderborg], [flensburg, husum], [husum], []]
    points = []
    for areas in memberships:
        doc = sample(entity)
        payload = next(iter(plan(doc).desired.values()))[1]
        payload[key] = [str(area) for area in areas]
        # A different organization mode must never grant membership.
        if entity == "organization":
            other = "activity_area_ids" if mode == "home" else "home_area_ids"
            payload[other] = [str(flensburg), str(aabenraa), str(sonderborg)]
        points.append({"score": 0.8, "payload": payload})
    requested = {
        "single": {"area_id": flensburg},
        "one_item": {"area_ids": [flensburg]},
        "multiple": {"area_ids": [flensburg, aabenraa, sonderborg]},
        "duplicates": {"area_ids": [flensburg, aabenraa, flensburg, sonderborg]},
        "no_matches": {"area_ids": [elsewhere]},
    }[selection]
    expected_indices = {
        "single": [0, 3],
        "one_item": [0, 3],
        "multiple": [0, 1, 2, 3],
        "duplicates": [0, 1, 2, 3],
        "no_matches": [],
    }[selection]
    expected = {UUID(points[i]["payload"]["entity_id"]) for i in expected_indices}

    def serve(request):
        body = json.loads(request.content)
        conditions = body["filter"]["must"]
        assert len(conditions) == 1  # Repeated must clauses would mean AND.
        condition = conditions[0]
        assert condition["key"] == key
        values = condition["match"]["any"]
        assert len(values) == len(set(values))
        matches = [p for p in points if set(p["payload"][key]).intersection(values)]
        return httpx.Response(200, json={"result": {"points": matches[: body["limit"]]}})

    qdrant = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity=entity)
    try:
        hits = await qdrant.search([1.0] * 1024, 10, organization_mode=mode, **requested)
    finally:
        await qdrant.http.close()
    allowed = {UUID(p["payload"]["entity_id"]) for p in points}
    assert {UUID(h["payload"]["entity_id"]) for h in hits} == expected
    for candidates in (hits, points):  # Also reject out-of-area provider results defensively.
        evidence = semantic_hits(
            candidates, allowed, MODEL, entity=entity, organization_mode=mode, **requested
        )
        assert {h.entity_id for h in evidence} == expected
        assert all(h.score == 0.8 for h in evidence)


@pytest.mark.parametrize(
    "entity,kwargs,error",
    [
        ("event", {"area_ids": []}, "invalid_area_count"),
        ("event", {"area_ids": [uuid4()] * 51}, "invalid_area_count"),
        ("event", {"area_id": uuid4(), "area_ids": [uuid4()]}, "conflicting_area_filters"),
        ("event", {"area_id": uuid4(), "area_ids": []}, "conflicting_area_filters"),
        ("organization", {"area_ids": [uuid4()]}, "organization_area_mode_required"),
        ("event", {"area_ids": [uuid4()], "organization_mode": "home"}, "unexpected_organization"),
        (
            "venue",
            {"area_ids": [uuid4()], "organization_mode": "activity"},
            "unexpected_organization",
        ),
        ("organization", {"organization_mode": "home"}, "area_id_required"),
    ],
)
async def test_invalid_area_selection_rejected_before_transport(settings, entity, kwargs, error):
    def serve(request):
        pytest.fail("Invalid filters must not reach Qdrant")

    qdrant = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity=entity)
    try:
        with pytest.raises(ValueError, match=error):
            await qdrant.search([1.0] * 1024, 10, **kwargs)
    finally:
        await qdrant.http.close()
    with pytest.raises(ValueError, match=error):
        area_filter(entity, **kwargs)
    with pytest.raises(ValueError, match=error):
        semantic_hits([], set(), MODEL, entity=entity, **kwargs)


async def test_pilot_index_still_rejects_area_filters(settings):
    qdrant = Qdrant(vector_settings(settings), "jina-v3")
    try:
        with pytest.raises(ValueError, match="semantic_collection_required"):
            await qdrant.search([1.0] * 1024, 10, area_ids=[uuid4()])
    finally:
        await qdrant.http.close()


def occurrence_document(**changes):
    from tests.conftest import uid

    row = {
        "entity_id": uid(30),
        "organization_id": uid(10),
        "title": "Culture",
        "status": "released",
        "participation_info": "Gemeinsam gestalten",
        "ticket_link": "https://example.test/event-tickets",
        "price_type": "free",
        "source_link": "https://example.test/source",
    }
    occurrences = [
        {
            "occurrence_id": uid(40),
            "venue_id": uid(20),
            "space_id": uid(25),
            "venue_name": "Venue A",
            "space_name": "Room A",
            "area_names": ["Town A"],
            "venue_accessibility": "Venue A stufenlos",
            "space_accessibility": "Room A erreichbar",
            "date_accessibility": "Assistenz am Termin A",
            "ticket_link": None,
        },
        {
            "occurrence_id": uid(41),
            "venue_id": uid(21),
            "space_id": uid(26),
            "venue_name": "Venue B",
            "space_name": "Room B",
            "area_names": ["Town B"],
            "venue_accessibility": "Venue B stufenlos",
            "space_accessibility": None,
            "date_accessibility": "Assistenz am Termin B",
            "ticket_link": "https://example.test/date-b",
        },
    ]
    return event_document(
        row,
        {
            "venue_names": ["Venue A", "Venue B"],
            "space_names": ["Room A", "Room B"],
            "area_names": ["Town A", "Town B"],
            "accessibility": ["UNSCOPED MUST NOT SURVIVE"],
            "occurrences": occurrences,
            **changes,
        },
    )


def test_sections_and_short_chunks_keep_explicit_source_scope():
    doc = occurrence_document()
    assert len(doc.sections) > 5
    content = next(s for s in doc.sections if s.kind == "content")
    assert content.context.scope == "event"
    assert all(word not in content.text for word in ("Venue", "Room", "Town", "Assistenz"))
    assert "UNSCOPED" not in doc.model_dump_json()
    payloads = [p for _, p in plan(doc).desired.values()]
    assert all(p["evidence_contexts"] for p in payloads)
    for payload in payloads:
        text = payload["chunk_text"]
        assert not ("Venue A" in text and "Venue B" in text)
        contexts = payload["evidence_contexts"]
        if "Venue A stufenlos" in text:
            assert contexts[0]["scope"] == "venue" and contexts[0]["space_id"] is None
        if "Room A erreichbar" in text:
            assert contexts[0]["scope"] == "space"
        if "Assistenz" in text or "/date-b" in text or "/event-tickets" in text:
            assert contexts[0]["scope"] == "occurrence"
        if payload["chunk_kind"] in {"participation", "additional"} or "kostenlos" in text:
            assert contexts == [
                {"scope": "event", "venue_id": None, "space_id": None, "occurrence_id": None}
            ]


def test_identical_scoped_text_shares_vector_with_explicit_context_union():
    from app.research.evidence_context import EvidenceContext
    from tests.conftest import uid

    doc = sample("event")
    scopes = [EvidenceContext(scope="venue", venue_id=uid(i)) for i in (20, 21)]
    doc.sections = [
        Section(kind="accessibility", text="Barrierefreiheit: Stufenlos", context=c) for c in scopes
    ]
    first = plan(doc)
    assert len(first.desired) == 1
    chunk, payload = next(iter(first.desired.values()))
    assert chunk.contexts == scopes
    assert payload["evidence_contexts"] == [c.model_dump(mode="json") for c in scopes]
    doc.sections.reverse()
    assert plan(doc).desired == first.desired
    existing = {i: p for i, (_, p) in first.desired.items()}
    doc.sections.pop()
    changed = plan(doc, existing)
    assert len(changed.metadata) == 1
    assert not changed.embed and not changed.delete


def test_v3_upgrade_reuses_text_vectors_and_replaces_changed_sections():
    doc = sample("event")
    first = plan(doc)
    existing = {
        i: {**p, "document_schema_version": "event-public-v3"}
        for i, (_, p) in first.desired.items()
    }
    for payload in existing.values():
        del payload["evidence_contexts"]
    upgrade = plan(doc, existing)
    assert len(upgrade.metadata) == 1 and not upgrade.embed
    doc.sections[0].text += " Changed text"
    replacement = plan(doc, existing)
    assert replacement.new == 1 and len(replacement.embed) == len(replacement.delete) == 1


@pytest.mark.parametrize("tamper", ["missing", "other_venue", "global", "wrong_kind", "text"])
def test_plan_rejects_forged_context_and_kind(tamper):
    from app.research.evidence_context import EvidenceContext
    from tests.conftest import uid

    doc = occurrence_document()
    chunks = prepare(doc)
    chunk = next(c for c in chunks[str(doc.entity_id)] if c.chunk_kind == "accessibility")
    if tamper == "missing":
        chunk.contexts = []
    elif tamper == "other_venue":
        chunk.contexts = [EvidenceContext(scope="venue", venue_id=uid(999))]
    elif tamper == "global":
        chunk.contexts = [EvidenceContext(scope="event")]
    elif tamper == "wrong_kind":
        chunk.chunk_kind = "content"
    else:
        chunk.text = "Text not from source"
        chunk.content_hash = content_hash(chunk.text)
    with pytest.raises(ValueError, match="unmatched"):
        plan_changes([doc], chunks, {}, MODEL, complete=True, entity="event")


async def test_context_survives_encoder_json_wire(settings):
    # Exercise the real /chunks handler with a synthetic tokenizer, no model load.
    import importlib.util

    from tests.test_vector_index import ENCODER_PATH

    spec = importlib.util.spec_from_file_location("context_encoder", ENCODER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = module.Runtime()
    runtime.load = lambda key: None
    runtime.count = lambda value: len(value.split()) + 2
    app = module.create_app(runtime, "x" * 48)
    settings = vector_settings(settings)
    from pydantic import SecretStr

    settings.embedding_api_key = SecretStr("x" * 48)
    encoder = Encoder(settings, "jina-v3", httpx.ASGITransport(app=app))
    doc = occurrence_document()
    try:
        prepared = await encoder.prepare([doc])
        result = plan_changes([doc], prepared, {}, MODEL, complete=True, entity="event")
        assert result.desired == plan(doc).desired
        response = await encoder.http.request(
            "POST",
            "/chunks",
            {
                "model": "jina-v3",
                "documents": [
                    {
                        "entity_id": str(doc.entity_id),
                        "sections": [{"kind": "content", "text": "Legacy public text"}],
                    }
                ],
            },
        )
        assert "contexts" not in response["documents"][0]["chunks"][0]
    finally:
        await encoder.http.close()


@pytest.mark.integration
async def test_two_occurrences_extract_rehydrate_and_filter(db_connection, settings, now):
    from datetime import date

    from app.repositories.research import rehydrate_semantic_events
    from app.research.semantic_evidence import contextualize_event_hit
    from app.schemas.research import SemanticResearchFilters
    from tests.conftest import uid

    await db_connection.execute(
        text("""UPDATE uranus.venue SET accessibility_summary=
        CASE WHEN uuid=:a THEN 'Pilkentafel stufenlos erreichbar' ELSE NULL END
        WHERE uuid IN (:a,:b)"""),
        {"a": uid(20), "b": uid(21)},
    )
    await db_connection.execute(
        text("""UPDATE uranus.event_date
        SET release_status='draft' WHERE event_uuid=:id"""),
        {"id": uid(30)},
    )
    for key, day, venue, space in [(9040, 1, 20, 25), (9041, 2, 21, None)]:
        await db_connection.execute(
            text("""INSERT INTO uranus.event_date
            (uuid,event_uuid,start_date,venue_uuid,space_uuid,release_status,accessibility_info)
            VALUES (:id,:event,:day,:venue,:space,'released',:access)"""),
            {
                "id": uid(key),
                "event": uid(30),
                "day": date(2030, 1, day),
                "venue": uid(venue),
                "space": uid(space) if space else None,
                "access": f"Assistenz an Tag {day}",
            },
        )
    docs, _ = await extract_events(db_connection, None, settings, now, semantic=True)
    doc = next(d for d in docs if d.entity_id == uid(30))
    points = [
        {"score": 0.9 if "Pilkentafel" in p["chunk_text"] else 0.4, "payload": p}
        for _, p in plan(doc).desired.values()
    ]
    hit = semantic_hits(points, {uid(30)}, MODEL, entity="event")[0]
    assert "Pilkentafel" in hit.winning_chunk.chunk_text
    for day, expected in [(1, True), (2, False)]:
        page = await rehydrate_semantic_events(
            db_connection,
            settings,
            SemanticResearchFilters(
                q="culture", from_date=date(2030, 1, day), to_date=date(2030, 1, day)
            ),
            [uid(30)],
            now,
        )
        record = page.items[0]
        assert page.occurrence_ids[record.entity_key] == uid(9039 + day)
        final = contextualize_event_hit(
            hit,
            venue_id=record.venue_id,
            space_id=record.space_id,
            occurrence_id=page.occurrence_ids[record.entity_key],
        )
        assert final is not None
        assert ("Pilkentafel" in final.winning_chunk.chunk_text) is expected
        assert final.score == (0.9 if expected else 0.4)
        assert "occurrence_ids" not in page.model_dump()


def test_shorter_text_inside_another_location_section_does_not_expand_scope():
    from app.research.evidence_context import EvidenceContext
    from tests.conftest import uid

    doc = sample("event")
    doc.sections = [
        Section(
            kind="accessibility",
            text="Barrierefreiheit: Stufenlos",
            context=EvidenceContext(scope="venue", venue_id=uid(20)),
        ),
        Section(
            kind="accessibility",
            text="Barrierefreiheit: Stufenlos mit Assistenz",
            context=EvidenceContext(scope="venue", venue_id=uid(21)),
        ),
    ]
    result = plan(doc)
    assert len(result.desired) == 2
    for chunk, payload in result.desired.values():
        assert len(payload["evidence_contexts"]) == 1
        assert chunk.contexts[0].venue_id == uid(21 if "Assistenz" in chunk.text else 20)


def test_long_scoped_sections_preserve_context_on_every_chunk():
    from app.research.evidence_context import EvidenceContext
    from tests.conftest import uid

    doc = sample("event")
    scope = EvidenceContext(scope="occurrence", occurrence_id=uid(40), venue_id=uid(20))
    doc.sections = [
        Section(
            kind="accessibility",
            text=" ".join(f"Stufenlos erreichbar in Abschnitt {i}." for i in range(700)),
            context=scope,
        )
    ]
    result = plan(doc)
    assert len(result.desired) > 2
    assert all(
        chunk.contexts == [scope] and chunk.token_count <= 480
        for chunk, _ in result.desired.values()
    )


def test_context_only_update_keeps_plan_idempotent():
    from app.research.evidence_context import EvidenceContext
    from tests.conftest import uid

    doc = sample("event")
    doc.sections = [
        Section(
            kind="accessibility",
            text="Barrierefreiheit: Stufenlos",
            context=EvidenceContext(scope="venue", venue_id=uid(20)),
        )
    ]
    old = {i: p for i, (_, p) in plan(doc).desired.items()}
    doc.sections[0].context = EvidenceContext(scope="space", venue_id=uid(20), space_id=uid(25))
    update = plan(doc, old)
    assert update.metadata and not update.embed and not update.delete
    applied = {i: p for i, (_, p) in update.desired.items()}
    second = plan(doc, applied)
    assert second.unchanged == 1 and not second.metadata and not second.embed
