"""Public evidence boundaries: provenance does not require licensed excerpts."""

import json
from pathlib import Path
from typing import get_args

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.errors import APIError
from app.schemas.project_knowledge import AnswerResponse, FactKey
from app.schemas.research_domain import FactKey as PlannerFactKey
from app.schemas.research_domain import KnowledgePlan, PlanEnvelopeV4
from app.services.research_domain_client import ResearchDomainClient
from tests.test_research_domain_contract import FACTS
from tests.test_research_unified import PATH, synthetic_evidence


def test_public_answer_schema_matches_reviewed_knowledge():
    fixture = json.loads(Path("tests/fixtures/project_knowledge_answer_schema.json").read_text())
    assert fixture["commit"] == "adcb6b917850b2656fd6145181ad47c3c4d3becd"
    assert AnswerResponse.model_json_schema() == fixture["schema"]
    assert get_args(FactKey) == get_args(PlannerFactKey) == FACTS
    assert set(fixture["schema"]["$defs"]) == {"Evidence", "Fact"}


@pytest.mark.parametrize("include_null", [False, True])
@pytest.mark.parametrize("redistribution_allowed", [False, True])
async def test_supported_metadata_only_evidence_passes_through_api(
    client, headers, monkeypatch, include_null, redistribution_allowed
):
    answer = synthetic_evidence("embedding_component", excerpt_included=False)
    payload = answer.model_dump(mode="json", exclude_none=not include_null)
    payload["evidence"][0]["evidence_redistribution_allowed"] = redistribution_allowed
    question = "  Welche Komponente erzeugt die Embeddings?\n"
    plan = KnowledgePlan(fact="embedding_component", knowledge_query=question)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        assert "cookie" not in request.headers
        if request.url.path == "/v4/plan":
            return httpx.Response(
                200,
                json=PlanEnvelopeV4(original_query=question, plan=plan).model_dump(mode="json"),
            )
        assert str(request.url) == "http://127.0.0.1:6336/evidence-answer"
        assert json.loads(request.content) == {"query": question, "fact": plan.fact}
        assert request.headers["authorization"] == "Bearer " + "k" * 32
        return httpx.Response(200, json=payload)

    app = client._transport.app
    settings = app.state.settings
    settings.research_domain_enabled = True
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("p" * 32)
    settings.research_knowledge_url = "http://127.0.0.1:6336"
    settings.research_knowledge_api_key = SecretStr("k" * 32)
    provider = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(app.state, "research_domain", provider)

    def forbidden(*args):
        raise AssertionError("Knowledge must not open a database")

    monkeypatch.setattr("app.services.research_unified.get_connection", forbidden)
    monkeypatch.setattr("app.services.research_unified.connect_admin", forbidden)
    try:
        response = await client.post(PATH, json={"query": question}, headers=headers)
        assert response.status_code == 200, response.text
        expected = answer.model_dump(mode="json")
        expected["evidence"][0]["evidence_redistribution_allowed"] = redistribution_allowed
        assert response.json() == expected  # All provenance/license/graph metadata survives.
        assert response.json()["supported"] is True
        assert response.json()["evidence"][0]["chunk_text"] is None
        assert len(calls) == 2
    finally:
        await provider.close()


def invalid_answers():
    for key, value in (
        ("chunk_text", None),
        ("chunk_text", ""),
        ("evidence_redistribution_allowed", False),
        ("excerpt_included", False),
        ("evidence_available", False),
        ("content_hash", "invalid"),
        ("content_hash", "0" * 64),
        ("source_url", "https://untrusted.invalid/source"),
        ("commit_sha", "invalid"),
        ("line_end", 0),
        ("line_start", 2),
        ("path", "../README.md"),
        ("assertions", []),
        ("graph_assertions", []),
        ("index_owner", "kulturbytes-project-knowledge-v1"),
        ("schema_version", "project-chunk-v1"),
        ("embedding_version", "internal"),
        ("unit", "internal"),
        ("graph_node_ids", []),
    ):
        payload = synthetic_evidence("embedding_component").model_dump(mode="json")
        payload["evidence"][0][key] = value
        yield f"evidence-{key}-{value}", payload
    payload = synthetic_evidence("embedding_component").model_dump(mode="json")
    del payload["evidence"][0]["chunk_text"]
    yield "missing-included-excerpt", payload
    for tamper in ("reference", "duplicate", "unknown", "commits", "support", "reason"):
        payload = synthetic_evidence("embedding_component", excerpt_included=False).model_dump(
            mode="json", exclude_none=True
        )
        if tamper == "reference":
            payload["facts"][0]["evidence_ids"] = ["missing-evidence"]
        elif tamper == "duplicate":
            payload["evidence"].append(dict(payload["evidence"][0]))
        elif tamper == "unknown":
            payload["facts"][0]["key"] = "unknown"
        elif tamper == "commits":
            payload["indexed_commits"] = {}
        elif tamper == "support":
            payload["supported"] = False
        else:
            payload["reason"] = "no_explicit_evidence"
        yield tamper, payload
    payload = synthetic_evidence("embedding_component", excerpt_included=False).model_dump(
        mode="json", exclude_none=True
    )
    payload["evidence"][0]["content_hash"] = "invalid"
    yield "invalid-withheld-hash", payload


@pytest.mark.parametrize("case,payload", list(invalid_answers()))
async def test_invalid_public_answer_is_rejected_without_repair(settings, caplog, case, payload):
    with pytest.raises(ValidationError):
        AnswerResponse.model_validate(payload)
    settings.research_knowledge_url = "http://127.0.0.1:6336"
    settings.research_knowledge_api_key = SecretStr("k" * 32)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)

    provider = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as exc:
            await provider.answer(
                KnowledgePlan(fact="embedding_component", knowledge_query="original question")
            )
        assert (exc.value.status, exc.value.code) == (502, "research_domain_invalid")
        assert len(calls) == 1
        assert "Synthetic acceptance fixture" not in str(exc.value) + caplog.text
    finally:
        await provider.close()


@pytest.mark.parametrize("status", [422, 500, 502, 503])
async def test_knowledge_error_body_is_not_exposed_or_retried(settings, caplog, status):
    settings.research_knowledge_url = "http://127.0.0.1:6336"
    settings.research_knowledge_api_key = SecretStr("k" * 32)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-knowledge-error")

    provider = ResearchDomainClient(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as exc:
            await provider.answer(
                KnowledgePlan(fact="embedding_component", knowledge_query="original question")
            )
        assert (exc.value.status, exc.value.code) == (503, "research_domain_unavailable")
        assert "private-knowledge-error" not in str(exc.value) + caplog.text
        assert len(calls) == 1
    finally:
        await provider.close()
