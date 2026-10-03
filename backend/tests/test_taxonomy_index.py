"""Operator index/benchmark safety without live encoder, Qdrant or container dependencies."""

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.research.taxonomy import MODEL, corpus_hash, documents
from app.research.taxonomy_benchmark import Benchmark, Case, Measurement, Measurements, calibrate
from app.research.taxonomy_index import sync_taxonomy
from app.research.taxonomy_policy import confident
from app.research.taxonomy_transport import TaxonomyQdrant
from tests.test_research_plan_execution import execution_source as execution_source_fixture
from tests.test_research_taxonomy import taxonomy_source as taxonomy_source_fixture
from tests.test_taxonomy_semantic import payloads, vocabulary
from tests.test_taxonomy_semantic import retrieval as retrieval_fixture

retrieval = retrieval_fixture
taxonomy_source = taxonomy_source_fixture
execution_source = execution_source_fixture


async def test_sync_idempotent_rebuild_and_stale_deletion():
    qdrant, encoder = AsyncMock(), AsyncMock()
    qdrant.info.return_value = {}
    qdrant.points.return_value = {"stale": {}}
    encoder.embed.side_effect = lambda texts: [[1.0] for _ in texts]
    docs = documents(vocabulary())
    counts = await sync_taxonomy(qdrant, encoder, docs)
    assert counts == {"documents": 5, "upserted": 5, "deleted": 1, "unchanged": 0}
    points = [p for call in qdrant.upsert.await_args_list for p in call.args[0]]
    qdrant.delete.assert_awaited_once_with(["stale"])
    qdrant.points.return_value = {p["id"]: p["payload"] for p in points}
    encoder.reset_mock()
    assert (await sync_taxonomy(qdrant, encoder, docs))["unchanged"] == 5
    encoder.embed.assert_not_awaited()
    assert (await sync_taxonomy(qdrant, encoder, docs, rebuild=True))["upserted"] == 5
    assert all("query" not in call.kwargs for call in encoder.embed.await_args_list)


async def test_failed_upsert_never_deletes_stale_points():
    qdrant, encoder = AsyncMock(), AsyncMock()
    qdrant.info.return_value = {}
    qdrant.points.return_value = {"stale": {}}
    encoder.embed.side_effect = ValueError("fixture_failure")
    with pytest.raises(ValueError):
        await sync_taxonomy(qdrant, encoder, documents(vocabulary()))
    qdrant.delete.assert_not_awaited()


async def test_plan_never_writes_and_empty_complete_snapshot_removes_stale():
    qdrant, encoder = AsyncMock(), AsyncMock()
    qdrant.info.return_value = {}
    qdrant.points.return_value = {"stale": {}}
    assert (await sync_taxonomy(qdrant, encoder, [], apply=False))["deleted"] == 1
    qdrant.delete.assert_not_awaited()
    qdrant.create.assert_not_awaited()
    encoder.embed.assert_not_awaited()
    await sync_taxonomy(qdrant, encoder, [])
    qdrant.delete.assert_awaited_once_with(["stale"])


@pytest.mark.parametrize("size,distance", [(384, "Cosine"), (1024, "Dot")])
async def test_collection_dimension_metric_mismatch(settings, retrieval, size, distance):
    qdrant = TaxonomyQdrant(
        settings,
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "result": {
                        "config": {"params": {"vectors": {"size": size, "distance": distance}}}
                    }
                },
            )
        ),
    )
    try:
        with pytest.raises(ValueError, match="incompatible"):
            await qdrant.info()
    finally:
        await qdrant.http.close()


async def test_foreign_or_old_model_payload_refuses_index_mutation(settings, retrieval):
    p = payloads()[0].model_dump(mode="json")
    p["embedding_version"] = "wrong"
    qdrant = TaxonomyQdrant(
        settings,
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "result": {
                        "points": [{"id": "foreign", "payload": p}],
                        "next_page_offset": None,
                    }
                },
            )
        ),
    )
    try:
        with pytest.raises(ValidationError):
            await qdrant.points()
    finally:
        await qdrant.http.close()


def measured():
    p = {p.key: p for p in payloads()}
    positive = Measurement(
        case=Case(query="synthetic positive", expected="event_type", label="Theater & Bühne"),
        expected_key="event_type:2",
        hits=((p["event_type:2"], 0.95), (p["genre:2:2004"], 0.5)),
    )
    ambiguous = Measurement(
        case=Case(query="synthetic ambiguous", expected="ambiguous"),
        expected_key=None,
        hits=((p["event_type:2"], 0.9), (p["genre:2:2004"], 0.89)),
    )
    negative = Measurement(
        case=Case(query="synthetic negative", expected="unresolved"),
        expected_key=None,
        hits=((p["event_type:2"], 0.4), (p["genre:2:2004"], 0.3)),
    )
    return Measurements(
        corpus_hash=corpus_hash(documents(vocabulary())),
        benchmark_hash="a" * 64,
        embedding_version=MODEL.version,
        rows=(positive, ambiguous, negative) * 4,
    )


def test_calibration_uses_observations_and_requires_all_cases():
    values = measured()
    policy = calibrate(values)
    for row in values.rows:
        selected = confident(list(row.hits), policy)
        assert (
            len(selected) == {"event_type": 1, "ambiguous": 2, "unresolved": 0}[row.case.expected]
        )
    # Identical score distributions with contradictory judgments cannot produce
    # a production policy, regardless of how convenient a guessed threshold is.
    contradictory = values.rows[0].model_copy(
        update={"case": Case(query="contradiction", expected="unresolved"), "expected_key": None}
    )
    with pytest.raises(ValueError, match="no_safe_thresholds"):
        calibrate(values.model_copy(update={"rows": (*values.rows, contradictory)}))


def test_benchmark_is_bounded_reviewable_and_contains_no_fabricated_ids():
    benchmark = Benchmark.model_validate_json(
        Path("tests/fixtures/taxonomy_benchmark.json").read_bytes()
    )
    assert len(benchmark.cases) == 23
    assert {c.query for c in benchmark.cases} >= {
        "Theater",
        "Schauspiel",
        "Bühne",
        "Theateraufführung",
        "Circus",
        "Zirkus",
        "Zirkustheater",
        "Musical",
        "Musiktheater",
        "Drama",
        "Komödie",
        "Jazz",
        "Rock",
        "Kultur",
        "Veranstaltung",
        "Show",
        "Kunst",
        "Treffen",
        "Kinder",
        "Musik",
    }
    assert all("id" not in c.model_dump() for c in benchmark.cases)


async def test_current_postgres_vocabulary_retains_translations_and_public_identity(
    taxonomy_source,
):
    from app.repositories.research_taxonomy import load_taxonomy

    docs = documents(await load_taxonomy(taxonomy_source))
    by_key = {d.key: d for d in docs}
    assert by_key["event_type:1"].canonical_label == "Konzert"
    assert by_key["genre:1:1003"].parent_label == "Konzert"
    assert by_key["genre:1:1003"].genre_id == "1003"
    assert "en: Jazz EN." in by_key["genre:1:1003"].embedding_text


async def test_scroll_is_bounded_even_when_provider_returns_empty_pages(settings, retrieval):
    calls = 0

    def transport(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"result": {"points": [], "next_page_offset": calls}})

    qdrant = TaxonomyQdrant(settings, httpx.MockTransport(transport))
    try:
        with pytest.raises(ValueError, match="page_limit"):
            await qdrant.points()
        assert calls == 65
    finally:
        await qdrant.http.close()
