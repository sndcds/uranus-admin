"""Gateway contract, safe failures and the unchanged Research trust boundary."""

import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import APIError
from app.research.search_gateway import retrieve_candidates
from tests.conftest import uid

URL = "https://search.kulturbytes.de/search"


def candidate(key: int = 30, score: object = 0.8, status: str = "released") -> dict[str, object]:
    return {"entity_id": str(uid(key)), "score": score, "status": status}


async def test_candidate_gateway_keeps_ranked_ids_and_safe_request_contract() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        results = [candidate(30, 0.1), candidate(32, 0.9, "draft"), candidate(30, 0.8)]
        return httpx.Response(200, json={"results": results, "count": len(results)})

    assert await retrieve_candidates(
        URL, "private query", transport=httpx.MockTransport(respond)
    ) == [uid(32), uid(30)]
    request = calls[0]
    assert str(request.url) == URL and request.method == "POST"
    assert json.loads(request.content) == {"query": "private query", "limit": 10}
    for header in ("authorization", "cookie", "api-key", "x-admin-csrf"):
        assert header not in request.headers


@pytest.mark.parametrize("status", [429, 500])
async def test_candidate_gateway_safe_provider_failure(status: int) -> None:
    with pytest.raises(APIError) as error:
        await retrieve_candidates(
            URL,
            "query",
            transport=httpx.MockTransport(lambda _: httpx.Response(status, text="provider-secret")),
        )
    assert "provider-secret" not in error.value.message


async def test_candidate_gateway_safe_timeout() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider-secret", request=request)

    with pytest.raises(APIError) as error:
        await retrieve_candidates(URL, "query", transport=httpx.MockTransport(respond))
    assert "provider-secret" not in error.value.message


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

    def respond(request: httpx.Request) -> httpx.Response:
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
