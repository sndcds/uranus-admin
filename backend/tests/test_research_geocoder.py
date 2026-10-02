"""Private transport boundaries and untrusted location-context validation."""

import json

import httpx
import pytest
from pydantic import ValidationError

from app.clients.research_geocoder import MAX_RESPONSE_BYTES, ResearchGeocoderClient
from app.config import Settings
from app.errors import APIError
from app.schemas.research_location import ResearchQueryRequest
from tests.test_research_planner import configured

PLACE = {
    "display_name": "Bachstraße, Flensburg",
    "place_type": "street",
    "osm_type": "way",
    "osm_id": 123,
    "latitude": 54.79,
    "longitude": 9.43,
    "address": {"road": "Bachstraße", "city": "Flensburg"},
    "bbox": [54.78, 9.42, 54.80, 9.44],
}


def client_for(handler):
    return ResearchGeocoderClient(
        configured(research_geocoder_api_key="g" * 32), transport=httpx.MockTransport(handler)
    )


async def test_transport_has_only_controlled_fields_and_service_auth():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + "g" * 32
        assert "cookie" not in request.headers
        payload = json.loads(request.content) if request.content else {}
        if request.url.path == "/search":
            result = {"query": payload["query"], "items": [PLACE]}
        elif request.url.path == "/ready":
            result = {"status": "ready"}
        else:
            result = PLACE
        return httpx.Response(200, json=result, headers={"set-cookie": "secret=never-forward"})

    client = client_for(respond)
    try:
        assert len(await client.search("Bachstraße Flensburg")) == 1
        assert await client.reverse(54.79, 9.43) is not None
        assert await client.lookup("W", 123) is not None
        assert await client.ready()
        assert [r.url.path for r in calls] == ["/search", "/reverse", "/lookup", "/ready"]
        assert json.loads(calls[0].content) == {"query": "Bachstraße Flensburg", "limit": 5}
        assert json.loads(calls[1].content) == {"latitude": 54.79, "longitude": 9.43}
    finally:
        await client.close()


@pytest.mark.parametrize("status", [301, 302, 401, 403, 422, 500, 503])
async def test_upstream_errors_are_safe_without_redirects(status):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://evil.invalid"}, text="secret address"
        )

    client = client_for(respond)
    try:
        with pytest.raises(APIError) as exc:
            await client.search("secret query")
        assert exc.value.code == "geocoder_unavailable" and exc.value.status == 503
        assert "secret" not in str(exc.value)
        assert len(calls) == 1
    finally:
        await client.close()


async def test_no_match_and_invalid_body():
    for response in [httpx.Response(404), httpx.Response(200, json={"query": "x", "items": []})]:
        client = client_for(lambda _, result=response: result)
        try:
            assert await client.search("x") == []
        finally:
            await client.close()
    for response in [
        httpx.Response(200, json={"query": "other", "items": []}),
        httpx.Response(200, json={"query": "x", "items": [{"latitude": 91}]}),
        httpx.Response(
            200,
            content=b"x" * (MAX_RESPONSE_BYTES + 1),
            headers={"content-type": "application/json"},
        ),
    ]:
        client = client_for(lambda _, result=response: result)
        try:
            with pytest.raises(APIError):
                await client.search("x")
        finally:
            await client.close()


async def test_timeout_maps_to_unavailable():
    def respond(request):
        raise httpx.ReadTimeout("private")

    client = client_for(respond)
    try:
        with pytest.raises(APIError) as exc:
            await client.search("x")
        assert exc.value.code == "geocoder_unavailable"
    finally:
        await client.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:6337",
        "http://localhost:6337",
        "http://127.0.0.1:6337/",
        "http://u:p@127.0.0.1:6337",
        "http://127.0.0.1:6337?q=x",
        "http://127.0.0.1:6337#x",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:6337\\x",
    ],
)
def test_reject_unsafe_origin(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_geocoder_url=url)


@pytest.mark.parametrize(
    "context",
    [
        dict(latitude=54.79),
        dict(longitude=9.43),
        dict(latitude=91, longitude=9),
        dict(latitude=True, longitude=9),
        dict(latitude="54", longitude=9),
        dict(latitude=float("nan"), longitude=9),
        dict(display_name=""),
        dict(osm_id=123),
        dict(url="https://evil.invalid"),
    ],
)
def test_reject_invalid_browser_context(context):
    with pytest.raises(ValidationError):
        ResearchQueryRequest(query="hier", location_context={"source": "manual", **context})


def test_manual_and_coordinate_context():
    for context in [dict(display_name="Flensburg"), dict(latitude=54.79, longitude=9.43)]:
        assert ResearchQueryRequest(query="hier", location_context={"source": "manual", **context})
