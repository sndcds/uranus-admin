"""Payload round trips and read-only, bounded diagnostics; synthetic records only."""

import argparse
import json
import math
import os
from copy import deepcopy
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.research import vector_index
from app.research.semantic_contracts import EffectiveLocation
from app.research.vector_diagnostics import metadata_diagnostics
from app.research.vector_sync import apply_changes, payloads_equal, plan_changes
from app.research.vector_transport import Qdrant
from tests.test_semantic_knowledge_index import MODEL, plan, prepare, sample
from tests.test_vector_index import vector_settings


def location_document():
    doc = sample("event")
    location = EffectiveLocation(
        effective_venue_id=uuid4(),
        effective_venue_name="Synthetic venue",
        effective_latitude=51.248178375505404,
        effective_longitude=9.123456789012345,
    )
    doc.payload.effective_locations = [location]
    for key, value in location.model_dump().items():
        setattr(doc.payload, key, value)
    doc.payload.venue_ids = [location.effective_venue_id]
    doc.payload.area_ids = [uuid4(), uuid4()]
    doc.payload.area_names = ["Area A", "Area B"]
    doc.payload.source_updated_at = "2026-09-29T10:00:00+00:00"
    return doc


def stored_payloads(doc):
    return {i: deepcopy(p) for i, (_, p) in plan(doc).desired.items()}


def qdrant_roundtrip(payload):
    # Measured with the CI-pinned Qdrant 1.19.1 image. serde_json's default
    # float parser maps this decimal to the adjacent representable float.
    result = json.loads(json.dumps(payload))
    result["effective_latitude"] = 51.24817837550541
    result["effective_locations"][0]["effective_latitude"] = 51.24817837550541
    return result


def test_metadata_diagnostics_raw_nested_types_redaction_and_bounds():
    doc = location_document()
    existing = stored_payloads(doc)
    for payload in existing.values():
        payload.update(
            chunk_text="SECRET_TEXT" * 10000,
            title="SECRET_TITLE",
            source_updated_at=None,
            space_ids=None,
        )
        payload["effective_locations"][0]["effective_venue_id"] = uuid4()
        payload["unexpected_secret_key"] = "SECRET_VALUE"
        payload.pop("language")
    before = deepcopy(existing)
    result = metadata_diagnostics(plan(doc, existing), existing, limit=1)
    fields = {f["field"]: f for f in result[0]["fields"]}
    assert fields["effective_locations[0].effective_venue_id"]["desired_type"] == "str"
    assert fields["effective_locations[0].effective_venue_id"]["qdrant_type"] == "UUID"
    assert fields["source_updated_at"]["qdrant_type"] == "NoneType"
    assert fields["language"]["qdrant_type"] == "missing"
    assert fields["space_ids"]["desired_summary"] == "length=0"
    assert "SECRET" not in json.dumps(result) and "unexpected_secret_key" not in json.dumps(result)
    assert existing == before
    for payload in existing.values():
        payload["embedding_version"] = "old"
    assert metadata_diagnostics(plan(doc, existing), existing) == []
    for limit in (0, 21):
        with pytest.raises(ValueError, match="limit"):
            metadata_diagnostics(plan(doc), {}, limit=limit)


def test_diagnostic_field_output_is_bounded():
    doc = location_document()
    doc.payload.area_names = [f"Area {i}" for i in range(100)]
    old = stored_payloads(doc)
    for payload in old.values():
        payload["area_names"].reverse()
    report = metadata_diagnostics(plan(doc, old), old)
    assert len(report[0]["fields"]) == 40
    assert report[0]["truncated"] is True


@pytest.mark.parametrize("command", ["sync", "reconcile", "benchmark"])
async def test_diagnostics_reject_writes_before_connections(settings, command):
    with pytest.raises(ValueError, match="bounded_plan"):
        await vector_index.run(
            argparse.Namespace(command=command, metadata_diagnostics=5), settings
        )


@pytest.mark.parametrize(
    "key",
    [
        "effective_latitude",
        "effective_longitude",
        "latitude",
        "longitude",
    ],
)
def test_only_coordinate_roundtrip_noise_is_equivalent(key):
    a = 51.248178375505404
    b = math.nextafter(a, math.inf)
    assert payloads_equal({key: a}, {key: b})
    assert not payloads_equal({key: a}, {key: math.nextafter(b, math.inf)})
    assert not payloads_equal({key: a}, {key: a + 1e-12})
    assert not payloads_equal({key: a}, {key: str(a)})
    assert not payloads_equal({key: a}, {key: None})
    assert not payloads_equal({key: a}, {key: float("nan")})
    assert not payloads_equal({key: a}, {key: float("inf")})
    assert not payloads_equal({"other": {key: a}}, {"other": {key: b}})
    assert not payloads_equal({"category_ids": [a]}, {"category_ids": [b]})
    assert payloads_equal({key: 54.0}, {key: 54})


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_updated_at", None),
        ("area_ids", []),
        ("area_names", ["Other"]),
        ("venue_ids", []),
        ("space_ids", [str(uuid4())]),
        ("next_date", "2026-10-01"),
        ("title", "Changed"),
        ("chunk_text", "Changed"),
        ("category_ids", [1]),
    ],
)
def test_meaningful_metadata_changes_are_not_hidden(field, value):
    doc = location_document()
    existing = {i: qdrant_roundtrip(p) for i, p in stored_payloads(doc).items()}
    for payload in existing.values():
        payload[field] = value
    assert plan(doc, existing).metadata
    assert not plan(doc, existing).embed


def test_order_nulls_ids_and_nested_changes_remain_significant():
    doc = location_document()
    old = stored_payloads(doc)
    payload = next(iter(old.values()))
    assert payloads_equal(payload, dict(reversed(list(payload.items()))))
    for field in ("area_ids", "area_names"):
        changed = deepcopy(payload)
        changed[field].reverse()
        assert not payloads_equal(payload, changed)
    changed = deepcopy(payload)
    changed.pop("language")  # Missing is not null.
    assert not payloads_equal(payload, changed)
    changed = deepcopy(payload)
    changed["effective_locations"][0]["effective_venue_id"] = str(uuid4())
    assert not payloads_equal(payload, changed)
    changed = deepcopy(payload)
    changed["effective_locations"][0]["effective_latitude"] += 1e-10
    assert not payloads_equal(payload, changed)
    changed = deepcopy(payload)
    changed["effective_locations"].append(deepcopy(changed["effective_locations"][0]))
    assert not payloads_equal(payload, changed)
    for field in ("content_hash", "embedding_model", "embedding_version"):
        changed = deepcopy(old)
        for p in changed.values():
            p[field] = "outdated"
        assert plan(doc, changed).embed
        assert not plan(doc, changed).metadata


def test_full_snapshot_1154_chunks_484_float_roundtrips():
    # Synthetic regression matching the reported counts, not production evidence.
    docs = [location_document() for _ in range(1154)]
    chunks = {k: v for doc in docs for k, v in prepare(doc).items()}
    first = plan_changes(docs, chunks, {}, MODEL, complete=True, entity="event")
    stored = {
        i: qdrant_roundtrip(p) if n < 484 else deepcopy(p)
        for n, (i, (_, p)) in enumerate(first.desired.items())
    }
    assert sum(p != first.desired[i][1] for i, p in stored.items()) == 484
    for _ in range(2):
        result = plan_changes(docs, chunks, stored, MODEL, complete=True, entity="event")
        assert result.counts() == {
            "chunks": 1154,
            "new": 0,
            "updated": 0,
            "metadata_updated": 0,
            "unchanged": 1154,
            "deleted": 0,
        }
    assert len(metadata_diagnostics(result, stored, limit=3)) == 3


async def test_reconcile_float_roundtrip_and_overwrite_are_idempotent(settings):
    doc = location_document()
    stored = stored_payloads(doc)
    for payload in stored.values():
        payload["obsolete_field"] = "remove on overwrite"
    writes = []

    def serve(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}
                    }
                },
            )
        assert request.method == "PUT"
        assert request.url.path.endswith("/points/payload")
        assert request.url.params["wait"] == "true"
        body = json.loads(request.content)
        writes.append(body)
        for identifier in body["points"]:
            stored[identifier] = qdrant_roundtrip(body["payload"])
        return httpx.Response(200, json={"result": {"status": "completed"}})

    class NoEmbedding:
        metrics = []

        async def embed(self, texts):
            pytest.fail("metadata-only reconciliation must not embed")

    q = Qdrant(vector_settings(settings), "jina-v3", httpx.MockTransport(serve), entity="event")
    try:
        first = plan(doc, stored)
        assert first.metadata and not first.embed and not first.delete
        await apply_changes(q, NoEmbedding(), first)
        second = plan(doc, stored)
        assert second.counts() == {
            "chunks": 1,
            "new": 0,
            "updated": 0,
            "metadata_updated": 0,
            "unchanged": 1,
            "deleted": 0,
        }
        await apply_changes(q, NoEmbedding(), second)
        assert len(writes) == 1
        assert all("obsolete_field" not in p for p in stored.values())
        # The diagnostic still reveals raw round-trip differences after normalization.
        assert {f["field"] for f in metadata_diagnostics(second, stored)[0]["fields"]} == {
            "effective_latitude",
            "effective_locations[0].effective_latitude",
        }
    finally:
        await q.http.close()


@pytest.mark.integration
async def test_real_qdrant_semantic_metadata_roundtrip(settings):
    origin = os.environ.get("TEST_QDRANT_URL")
    if not origin:
        pytest.skip("Set TEST_QDRANT_URL for isolated Qdrant integration")
    assert urlsplit(origin).hostname in {"127.0.0.1", "localhost"}
    settings = vector_settings(settings)
    settings.qdrant_url = origin
    settings.qdrant_api_key = SecretStr("vector-test-only-key-with-more-than-32-characters")
    q = Qdrant(settings, "jina-v3", entity="event")
    # Never address a real semantic collection, even on a loopback instance.
    q.collection = "uranus_test_metadata_" + uuid4().hex
    q.path = "/collections/" + q.collection
    doc = location_document()

    class NoEmbedding:
        metrics = []

        async def embed(self, texts):
            pytest.fail("existing vectors must be reused")

    try:
        await q.create()
        await q.upsert(
            [
                {"id": i, "vector": [1.0] + [0.0] * 1023, "payload": {**p, "obsolete": True}}
                for i, p in stored_payloads(doc).items()
            ]
        )
        first = plan(doc, await q.points())
        assert first.metadata and not first.embed
        await apply_changes(q, NoEmbedding(), first)
        second = plan(doc, await q.points())
        assert second.unchanged == 1
        assert not second.embed and not second.metadata and not second.delete
        await apply_changes(q, NoEmbedding(), second)
        assert (await q.info())["points_count"] == 1
    finally:
        await q.http.request("DELETE", q.path, missing=True)
        await q.http.close()
