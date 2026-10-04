"""Operator index/benchmark safety without live encoder, Qdrant or container dependencies."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from app.research.taxonomy import MODEL, corpus_hash, documents
from app.research.taxonomy_benchmark import (
    Benchmark,
    Case,
    Measurement,
    Measurements,
    calibrate,
    exact_matches,
    passes,
)
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
    assert counts == {"documents": 6, "upserted": 6, "deleted": 1, "unchanged": 0}
    points = [p for call in qdrant.upsert.await_args_list for p in call.args[0]]
    qdrant.delete.assert_awaited_once_with(["stale"])
    qdrant.points.return_value = {p["id"]: p["payload"] for p in points}
    encoder.reset_mock()
    assert (await sync_taxonomy(qdrant, encoder, docs))["unchanged"] == 6
    encoder.embed.assert_not_awaited()
    assert (await sync_taxonomy(qdrant, encoder, docs, rebuild=True))["upserted"] == 6
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


def reviewed(values, path):
    raw = Benchmark(cases=tuple(r.case for r in values.rows)).model_dump_json().encode()
    path.write_bytes(raw)
    return values.model_copy(update={"benchmark_hash": hashlib.sha256(raw).hexdigest()})


def measured():
    p = {p.key: p for p in payloads()}

    def row(query, kind, expected, label, key, same, cross=()):
        return Measurement(
            case=Case(query=query, requested_kind=kind, expected=expected, label=label),
            expected_key=key,
            hits=tuple((p[k], score) for k, score in same),
            cross_hits=tuple((p[k], score) for k, score in cross),
        )

    # Synthetic score matrix: exercises all stages, never production evidence.
    rows = (
        row(
            "theater",
            "event_type",
            "event_type",
            "Theater & Bühne",
            "event_type:2",
            [("event_type:2", 0.491), ("event_type:1", 0.3)],
            [("genre:2:2004", 0.472), ("genre:2:2003", 0.3)],
        ),
        row(
            "Musik",
            "event_type",
            "ambiguous",
            None,
            None,
            [("event_type:2", 0.9), ("event_type:1", 0.89)],
        ),
        row(
            "Treffen",
            "event_type",
            "unresolved",
            None,
            None,
            [("event_type:1", 0.367), ("event_type:2", 0.324)],
            [("genre:2:2004", 0.3), ("genre:2:2003", 0.2)],
        ),
        row(
            "Circus",
            "genre",
            "genre",
            "Zirkus-Theater",
            "genre:2:2003",
            [("genre:2:2003", 0.95), ("genre:2:2004", 0.5)],
        ),
        row(
            "cross-level paraphrase",
            "event_type",
            "genre",
            "Drama",
            "genre:2:2004",
            [("event_type:1", 0.2), ("event_type:2", 0.1)],
            [("genre:2:2004", 0.96), ("genre:2:2003", 0.6)],
        ),
        row("Jazz", "genre", "genre", "Jazz", "genre:1:1003", []),
    )
    return Measurements(
        version="taxonomy-measurements-v2",
        corpus_hash=corpus_hash(documents(vocabulary())),
        benchmark_hash="a" * 64,
        embedding_version=MODEL.version,
        documents=tuple(documents(vocabulary())),
        rows=rows * 2,
    )


def test_calibration_uses_observations_and_requires_all_cases(tmp_path):
    path = tmp_path / "reviewed.json"
    values = reviewed(measured(), path)
    policy = calibrate(values, path)
    assert policy.event_type is not None
    assert policy.genre is not None
    assert policy.cross_level is not None
    for row in values.rows:
        exact = exact_matches(row.case, list(values.documents))
        selected = confident(list(row.hits), policy.requested(row.case.requested_kind))
        if not selected:
            selected = confident(list(row.cross_hits), policy.cross_level)
        assert passes(row, exact or [p.key for p, _ in selected], exact=bool(exact))
    contradictory = values.rows[0].model_copy(
        update={
            "case": Case(query="contradiction", requested_kind="event_type", expected="unresolved"),
            "expected_key": None,
        }
    )
    values = reviewed(values.model_copy(update={"rows": (*values.rows, contradictory)}), path)
    with pytest.raises(ValueError, match="no_safe_thresholds"):
        calibrate(values, path)


def test_changed_review_and_exact_ambiguity_cannot_be_calibrated_away(tmp_path):
    path = tmp_path / "reviewed.json"
    values = reviewed(measured(), path)
    path.write_text("{}")
    with pytest.raises(ValueError):
        calibrate(values, path)
    jazz = values.rows[5].model_copy(
        update={
            "case": Case(query="Jazz", requested_kind="genre", expected="ambiguous"),
            "expected_key": None,
        }
    )
    values = reviewed(values.model_copy(update={"rows": (*values.rows, jazz)}), path)
    with pytest.raises(ValueError, match="exact_requires_review"):
        calibrate(values, path)


def test_benchmark_is_bounded_reviewable_and_contains_no_fabricated_ids():
    benchmark = Benchmark.model_validate_json(
        Path("tests/fixtures/taxonomy_benchmark.json").read_bytes()
    )
    assert len(benchmark.cases) == 24
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


async def test_measurement_uses_exact_first_and_separate_filtered_searches(tmp_path):
    from app.research.taxonomy import index_payload
    from app.research.taxonomy_benchmark import measure

    docs = documents(vocabulary())
    digest = corpus_hash(docs)
    p = {d.key: index_payload(d, digest) for d in docs}
    benchmark = Benchmark(
        cases=(
            Case(query="Jazz", requested_kind="genre", expected="genre", label="Jazz"),
            Case(
                query="Schauspiel",
                requested_kind="event_type",
                expected="genre",
                label="Schauspiel",
            ),
            Case(
                query="theater",
                requested_kind="event_type",
                expected="event_type",
                label="Theater & Bühne",
            ),
            Case(query="Treffen", requested_kind="event_type", expected="unresolved"),
            Case(query="Musik", requested_kind="event_type", expected="ambiguous"),
        )
        * 2
    )
    path, output = tmp_path / "benchmark.json", tmp_path / "measurements.json"
    path.write_text(benchmark.model_dump_json())
    qdrant, encoder = AsyncMock(), AsyncMock()
    qdrant.info.return_value = {}
    qdrant.points.return_value = {x.point_id: x.model_dump(mode="json") for x in p.values()}
    encoder.embed.return_value = [[1.0]]

    def query(vector, *, expected_kind):
        assert vector == [1.0]
        return [
            {"id": x.point_id, "score": 0.5, "payload": x.model_dump(mode="json")}
            for x in p.values()
            if x.kind == expected_kind
        ]

    qdrant.query_taxonomy.side_effect = query
    await measure(qdrant, encoder, docs, path, output)
    measured = Measurements.model_validate_json(output.read_bytes())
    assert measured.documents == tuple(docs)
    assert encoder.embed.await_count == 6
    assert all(
        call.args[0][0] not in {"Jazz", "Schauspiel"} for call in encoder.embed.await_args_list
    )
    assert [call.kwargs["expected_kind"] for call in qdrant.query_taxonomy.await_args_list] == [
        "event_type",
        "genre",
    ] * 6
    assert all(
        not row.hits and not row.cross_hits
        for row in measured.rows
        if row.case.query in {"Jazz", "Schauspiel"}
    )


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("embedding_version", "old", "model_mismatch"),
        ("corpus_hash", "b" * 64, "corpus_mismatch"),
    ],
)
def test_calibration_rejects_stale_bindings(tmp_path, field, value, error):
    path = tmp_path / "reviewed.json"
    values = reviewed(measured(), path).model_copy(update={field: value})
    with pytest.raises(ValueError, match=error):
        calibrate(values, path)


def test_kunst_exact_interaction_keeps_authoritative_ambiguity():
    from app.research.taxonomy import LocalizedLabel, TaxonomyRow

    def row(identity):
        return TaxonomyRow(
            kind="event_type",
            id=identity,
            label="Kunst",
            labels=(LocalizedLabel(language="de", label="Kunst"),),
        )

    case = Case(query="Kunst", requested_kind="event_type", expected="exact_or_ambiguous")
    assert exact_matches(case, documents([row("8")])) == ["event_type:8"]
    assert exact_matches(case, documents([row("8"), row("9")])) == ["event_type:8", "event_type:9"]
    assert exact_matches(case, documents(vocabulary())) == []
    assert not passes(
        Measurement(case=case, expected_key=None, hits=(), cross_hits=()), ["event_type:2"]
    )
