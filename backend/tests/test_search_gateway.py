"""Gateway contract, safe failures and the unchanged Research trust boundary."""

import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import APIError
from app.logging import JsonFormatter
from app.research.search_gateway import retrieve_candidates
from app.services import semantic_search as service
from tests import test_semantic_search
from tests.conftest import uid

PATH = test_semantic_search.PATH
retrieval = test_semantic_search.retrieval

URL = "https://search.kulturbytes.de/search"


def candidate(key=30, score=0.8, status="released"):
    return {"entity_id": str(uid(key)), "score": score, "status": status}


@pytest.fixture
def gateway(settings, retrieval, monkeypatch):
    settings.semantic_search_url = URL
    settings.embedding_url = None
    settings.qdrant_url = None
    state = {"results": [candidate()], "failure": None, "requests": []}

    def respond(request):
        state["requests"].append(request)
        if state["failure"] == "timeout":
            raise httpx.ReadTimeout("provider-secret", request=request)
        if state["failure"] == "rate-limit":
            return httpx.Response(429, text="provider-secret", headers={"retry-after": "60"})
        if state["failure"]:
            return httpx.Response(500, text="provider-secret http://private.invalid")
        return httpx.Response(
            200, json={"results": state["results"], "count": len(state["results"])}
        )

    async def retrieve(url, query):
        return await retrieve_candidates(url, query, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(service, "retrieve_candidates", retrieve)
    return state


async def test_gateway_flows_through_rehydration_and_safe_metrics(
    client, headers, gateway, retrieval, caplog
):
    gateway["results"] = [candidate(30, 0.1), candidate(32, 0.9, "draft"), candidate(30, 0.8)]
    with caplog.at_level("INFO", logger="admin.research"):
        response = await client.get(
            PATH, headers=headers, params={"q": "private query", "category": 2}
        )
    assert response.status_code == 200
    assert len(gateway["requests"]) == 1
    request = gateway["requests"][0]
    assert str(request.url) == URL and request.method == "POST"
    assert json.loads(request.content) == {"query": "private query", "limit": 10}
    for header in ("authorization", "cookie", "api-key", "x-admin-csrf"):
        assert header not in request.headers
    assert not retrieval["requests"]  # no direct encoder/Qdrant call or fallback
    args = retrieval["rehydrate"].call_args.args
    assert args[2].category == 2 and args[3] == [uid(32), uid(30)]
    # Even cached 'draft' is just an ID candidate; PostgreSQL owns eligibility.
    assert response.json()["items"][0]["name"] == "Current"
    assert "score" not in response.text
    logged = json.loads(
        JsonFormatter().format(
            next(r for r in caplog.records if r.message == "research_semantic_search")
        )
    )
    assert logged["embedding_ms"] is None and logged["qdrant_ms"] is None
    assert logged["retrieval_ms"] >= 0
    assert logged["candidate_count"] == 2
    assert "private query" not in json.dumps(logged)


@pytest.mark.parametrize("failure", ["provider", "timeout", "rate-limit"])
async def test_gateway_safe_failure_without_fallback(client, headers, gateway, retrieval, failure):
    gateway["failure"] = failure
    response = await client.get(PATH, headers=headers, params={"q": "creative"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_semantic_unavailable"
    assert "provider-secret" not in response.text and "private.invalid" not in response.text
    assert len(gateway["requests"]) == 1
    retrieval["rehydrate"].assert_not_awaited()
    assert not retrieval["requests"]


async def test_gateway_cannot_bypass_license_gate(client, headers, gateway, settings):
    settings.semantic_search_noncommercial_jina = False
    assert (await client.get(PATH, headers=headers, params={"q": "creative"})).status_code == 503
    assert not gateway["requests"]


async def test_gateway_requires_auth(client, gateway):
    assert (await client.get(PATH, params={"q": "creative"})).status_code == 401
    assert not gateway["requests"]


async def test_gateway_overall_deadline(client, headers, gateway, retrieval, monkeypatch):
    async def slow(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(service, "retrieve_candidates", slow)
    monkeypatch.setattr(service, "REQUEST_TIMEOUT_SECONDS", 0.01)
    assert (await client.get(PATH, headers=headers, params={"q": "creative"})).status_code == 503
    retrieval["rehydrate"].assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [candidate()] * 11, "count": 11},
        {"results": [candidate()], "count": 0},
        {"results": [{"entity_id": "invalid", "score": 1}], "count": 1},
        {"results": [candidate(score="0.8")], "count": 1},
        {"results": [candidate(score=True)], "count": 1},
        {"results": [candidate()], "count": True},
        {"results": [candidate()], "count": "1"},
        [],
        {},
    ],
)
async def test_invalid_gateway_contract_fails_closed(payload):
    with pytest.raises(APIError):
        await retrieve_candidates(
            URL, "query", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://other.invalid/search"}),
        httpx.Response(200, text="provider-secret"),
        httpx.Response(200, content=b"x" * 65537, headers={"content-type": "application/json"}),
        httpx.Response(200, content=b"{", headers={"content-type": "application/json"}),
        httpx.Response(
            200,
            content=json.dumps({"results": [candidate(score=float("nan"))], "count": 1}).encode(),
            headers={"content-type": "application/json"},
        ),
    ],
)
async def test_invalid_http_responses_fail_closed(response):
    calls = []

    def respond(request):
        calls.append(request)
        return response

    with pytest.raises(APIError):
        await retrieve_candidates(URL, "query", transport=httpx.MockTransport(respond))
    assert len(calls) == 1  # redirects are never followed


async def test_empty_candidates_are_valid():
    assert (
        await retrieve_candidates(
            URL,
            "query",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"results": [], "count": 0})
            ),
        )
        == []
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://search.kulturbytes.de/search",
        "https://search.kulturbytes.de",
        URL + "?model=other",
        URL + "#fragment",
        URL + "/",
        "https://user:secret@search.kulturbytes.de/search",
        "https://*.kulturbytes.de/search",
    ],
)
def test_gateway_url_rejects_unsafe_configuration(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantic_search_url=url)


def test_gateway_does_not_require_unused_vector_credentials():
    settings = Settings(_env_file=None, semantic_search_url=URL)
    assert settings.semantic_search_url == URL
    assert settings.semantic_search_noncommercial_jina is False
