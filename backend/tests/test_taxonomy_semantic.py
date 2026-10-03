"""Synthetic canonical vocabulary and mocked vectors, not live model quality evidence."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import SecretStr

from app.repositories import research_resolution as resolver
from app.research.taxonomy import (
    COLLECTION,
    MODEL,
    LocalizedLabel,
    TaxonomyRow,
    corpus_hash,
    documents,
    index_payload,
)
from app.research.taxonomy_policy import ConfidencePolicy
from app.research.taxonomy_transport import TaxonomyQdrant
from app.research.vector_transport import Encoder
from app.services import taxonomy_resolution as service


def vocabulary():
    def row(kind, identity, label, english=None):
        labels = [LocalizedLabel(language="de", label=label)]
        if english:
            labels.append(LocalizedLabel(language="en", label=english))
        return TaxonomyRow(kind=kind, id=identity, label=label, labels=tuple(labels))

    return [
        row("event_type", "2", "Theater & Bühne", "Theatre & stage"),
        row("genre", "2:2003", "Zirkus-Theater", "Circus theatre"),
        row("genre", "2:2004", "Drama", "Drama"),
        row("event_type", "1", "Konzert", "Concert"),
        row("genre", "1:1003", "Jazz", "Jazz"),
    ]


def payloads():
    docs = documents(vocabulary())
    digest = corpus_hash(docs)
    return [index_payload(d, digest) for d in docs]


def policy():
    # Synthetic unit-only numbers. Never installed/configured as production defaults.
    return ConfidencePolicy(
        version="taxonomy-confidence-v1",
        embedding_version=MODEL.version,
        corpus_hash=corpus_hash(documents(vocabulary())),
        benchmark_hash="a" * 64,
        minimum_score=0.8,
        minimum_margin=0.1,
    )


@pytest.fixture
def retrieval(settings, monkeypatch, tmp_path):
    settings.research_taxonomy_policy_path = tmp_path / "policy.json"
    settings.research_taxonomy_policy_path.write_text(policy().model_dump_json())
    settings.semantic_search_noncommercial_jina = True
    settings.qdrant_url = "http://127.0.0.1:6333"
    settings.qdrant_api_key = SecretStr("fixture")
    settings.embedding_url = "http://127.0.0.1:6335"
    settings.embedding_api_key = SecretStr("fixture")
    docs = {p.key: p for p in payloads()}
    state = {
        "scores": [("event_type:2", 0.95), ("genre:2:2004", 0.7)],
        "missing": False,
        "mutate": None,
        "inventory": None,
    }
    requests = []

    def transport(req):
        requests.append(req)
        if req.url.path == "/embed":
            body = json.loads(req.content)
            assert body["kind"] == "query"
            return httpx.Response(
                200, json={"embedding_version": MODEL.version, "vectors": [[1.0] + [0.0] * 1023]}
            )
        assert req.url.path.startswith("/collections/" + COLLECTION)
        if req.method == "GET":
            if state["missing"]:
                return httpx.Response(404, json={})
            return httpx.Response(
                200,
                json={
                    "result": {
                        "config": {"params": {"vectors": {"size": 1024, "distance": "Cosine"}}}
                    }
                },
            )
        if req.url.path.endswith("/scroll"):
            points = [
                {"id": p.point_id, "payload": p.model_dump(mode="json")} for p in docs.values()
            ]
            if state["inventory"]:
                points = state["inventory"](points)
            return httpx.Response(
                200, json={"result": {"points": points, "next_page_offset": None}}
            )
        points = [
            {"id": docs[k].point_id, "payload": docs[k].model_dump(mode="json"), "score": score}
            for k, score in state["scores"]
        ]
        if state["mutate"]:
            state["mutate"](points)
        return httpx.Response(200, json={"result": {"points": points}})

    mock = httpx.MockTransport(transport)
    monkeypatch.setattr(service, "Encoder", lambda s, m: Encoder(s, m, mock))
    monkeypatch.setattr(service, "TaxonomyQdrant", lambda s: TaxonomyQdrant(s, mock))
    load = AsyncMock(return_value=vocabulary())
    monkeypatch.setattr(service, "load_taxonomy", load)
    return state, requests, load


@pytest.mark.parametrize(
    "query,key",
    [
        ("Theater", "event_type:2"),
        ("Schauspiel", "event_type:2"),
        ("Circus", "genre:2:2003"),
        ("Zirkus", "genre:2:2003"),
    ],
)
async def test_confident_revalidated_candidate(settings, retrieval, query, key, caplog):
    state, requests, load = retrieval
    state["scores"] = [(key, 0.95), ("genre:2:2004", 0.7)]
    found = await service.resolve_taxonomy_semantic(AsyncMock(), settings, query)
    assert len(found) == 1
    assert f"{found[0].entity_type}:{found[0].id}" == key
    assert "score" not in found[0].model_dump()
    assert "payload" not in found[0].model_dump()
    assert query not in caplog.text
    load.assert_awaited_once()
    assert len([r for r in requests if r.url.path == "/embed"]) == 1
    assert all(r.url.path == "/embed" or COLLECTION in r.url.path for r in requests)
    search = next(r for r in requests if r.url.path.endswith("/query"))
    assert json.loads(search.content)["params"] == {"exact": True}


@pytest.mark.parametrize("scores,count", [([0.9, 0.89], 2), ([0.6, 0.5], 0), ([0.81, 0.79], 0)])
async def test_ambiguity_weak_and_unsafe_margin(settings, retrieval, scores, count):
    state, _, _ = retrieval
    state["scores"] = list(zip(["event_type:2", "genre:2:2004"], scores, strict=True))
    found = await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Konzept")
    assert len(found) == count


@pytest.mark.parametrize(
    "mutation",
    [
        lambda points: points[0]["payload"].update(type_id="999"),
        lambda points: points[0]["payload"].update(parent_label="Falscher Typ"),
        lambda points: points[0]["payload"].update(embedding_version="old"),
        lambda points: points[0]["payload"].pop("embedding_version"),
        lambda points: points[0]["payload"].pop("index_owner"),
        lambda points: points[0].update(score=True),
        lambda points: points[0].update(id="wrong-point"),
        lambda points: points[0]["payload"].update(corpus_hash="b" * 64),
    ],
)
async def test_invalid_candidate_never_becomes_filter(settings, retrieval, mutation):
    state, _, _ = retrieval
    state["scores"] = [("genre:2:2003", 0.95), ("genre:2:2004", 0.7)]
    state["mutate"] = mutation
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Circus") == []


async def test_removed_sql_row_rejected(settings, retrieval):
    _, _, load = retrieval
    load.return_value = [r for r in vocabulary() if r.id != "2"]
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Theater") == []


async def test_partial_index_cannot_hide_runner_up(settings, retrieval):
    state, _, _ = retrieval
    state["inventory"] = lambda points: points[:1]
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Theater") == []


async def test_missing_collection_is_safe_unresolved(settings, retrieval):
    state, requests, load = retrieval
    state["missing"] = True
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Theater") == []
    load.assert_not_awaited()
    assert len(requests) == 1


async def test_expected_kind_and_parent_constrain_search_and_validation(settings, retrieval):
    _, requests, _ = retrieval
    assert (
        await service.resolve_taxonomy_semantic(
            AsyncMock(), settings, "Theater", expected_kind="genre", type_ids={"1"}
        )
        == []
    )
    body = json.loads(next(r for r in requests if r.url.path.endswith("/query")).content)
    assert body["filter"]["must"] == [
        {"key": "kind", "match": {"value": "genre"}},
        {"key": "type_id", "match": {"any": ["1"]}},
    ]


async def test_exact_wins_and_ambiguity_never_vector_tiebroken(settings, monkeypatch, tmp_path):
    settings.research_taxonomy_policy_path = tmp_path / "policy"
    semantic = AsyncMock()
    monkeypatch.setattr(resolver, "resolve_taxonomy_semantic", semantic)
    connection = AsyncMock()
    result = Mock()
    connection.execute.return_value = result
    for rows in [
        [{"id": "2", "label": "Theater & Bühne"}],
        [{"id": "2", "label": "Theater & Bühne"}, {"id": "3", "label": "Theater & Bühne"}],
    ]:
        result.mappings.return_value = rows
        assert len(
            await resolver.candidates(connection, "event_type", "Theater & Bühne", settings)
        ) == len(rows)
    semantic.assert_not_awaited()


def test_document_generation_deterministic_rich_multilingual_and_parent():
    a = documents(vocabulary())
    assert a == documents(list(reversed(vocabulary())))
    assert len({d.key for d in a}) == len(a) == len({d.point_id for d in a})
    by_key = {d.key: d for d in a}
    assert "Zugehörige Genres: Drama, Zirkus-Theater" in by_key["event_type:2"].embedding_text
    assert "en: Circus theatre" in by_key["genre:2:2003"].embedding_text
    assert by_key["genre:2:2003"].parent_label == "Theater & Bühne"
    assert by_key["genre:2:2003"].genre_id == "2003"
    assert "Schauspiel" not in by_key["event_type:2"].embedding_text


def test_no_runtime_string_table():
    for path in [Path("app/services/taxonomy_resolution.py"), Path("app/research/taxonomy.py")]:
        code = path.read_text()
        for query in ["Schauspiel", "Circus", "Zirkus", "Theater"]:
            assert query not in code


async def test_missing_policy_does_not_use_services(settings, monkeypatch):
    encoder = Mock(side_effect=AssertionError("disabled"))
    monkeypatch.setattr(service, "Encoder", encoder)
    assert settings.research_taxonomy_policy_path is None
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Theater") == []
    encoder.assert_not_called()


@pytest.mark.parametrize("case", ["unavailable", "timeout", "bad-policy"])
async def test_service_failures_never_become_unfiltered_execution(
    settings, retrieval, monkeypatch, case
):
    if case == "bad-policy":
        settings.research_taxonomy_policy_path.write_text('{"minimum_score": 0}')
    else:
        from app.errors import APIError

        error = (
            TimeoutError()
            if case == "timeout"
            else APIError(503, "vector_service_unavailable", "safe")
        )
        encoder = Mock()
        encoder.http.close = AsyncMock()
        encoder.embed = AsyncMock(side_effect=error)
        monkeypatch.setattr(service, "Encoder", lambda *a: encoder)
    assert await service.resolve_taxonomy_semantic(AsyncMock(), settings, "Theater") == []
