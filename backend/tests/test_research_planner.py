"""Synthetic wire fixtures; every planner call uses MockTransport, never inference."""

import asyncio
import json
import logging
from copy import deepcopy

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.auth.dependencies import get_identity
from app.auth.service import AdminPrincipal
from app.config import Settings
from app.errors import APIError
from app.logging import JsonFormatter
from app.main import create_app
from app.schemas.research_planner import ResearchPlanRequest
from app.services.research_planner import MAX_RESPONSE_BYTES, ResearchPlannerClient

QUERY = "Was ist heute Abend in Flensburg kulturell interessant?"
KEY = "synthetic-planner-service-key-for-tests-only"
URL = "http://127.0.0.1:8090"
PATH = "/api/v1/research/plan"
ENVELOPE = {
    "schema_version": "research-query-plan-v3",
    "prompt_version": "research-planner-v7",
    "model": "gpt-5.6-terra",
    "plan": {
        "original_query": QUERY,
        "intent": "recommend",
        "entity_type": "event",
        "semantic_query": "kulturell interessant",
        "area_query": "Flensburg",
        "venue_query": None,
        "organization_query": None,
        "event_type_queries": [],
        "category_queries": [],
        "genre_queries": [],
        "temporal": "today",
        "ordering": None,
        "limit": None,
        "explicit_from_date": None,
        "explicit_to_date": None,
        "time_of_day": "evening",
        "metric": "none",
        "group_by": "none",
        "comparison_targets": [],
        "semantic_focus": None,
        "requires_semantic_relevance": True,
        "answer_mode": "recommendation",
        "clarification": "none",
        "unsupported_reason": None,
    },
    "reference_date": "2026-09-30",
    "timezone": "Europe/Berlin",
    "diagnostics": {
        "request_id": "a" * 32,
        "planner_intent": "recommend",
        "planner_model": "gpt-5.6-terra",
        "planner_prompt_version": "research-planner-v7",
        "planner_ms": 4200.5,
        "total_ms": 4201.0,
    },
    "kind": "plan",
}


def configured(**values):
    return Settings(
        _env_file=None,
        research_planner_url=URL,
        research_planner_api_key=SecretStr(KEY),
        **values,
    )


def test_optional_complete_configuration():
    assert Settings(_env_file=None).research_planner_url is None
    assert configured().research_planner_timeout_seconds == 30
    assert KEY not in repr(configured())


@pytest.mark.parametrize(
    "values",
    [
        {"research_planner_url": URL},
        {"research_planner_api_key": KEY},
        *({"research_planner_timeout_seconds": value} for value in (0, 31)),
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **values)
    assert KEY not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8090",
        "https://example.com",
        "http://10.0.0.1:8090",
        "http://169.254.169.254",
        "http://127.0.0.1:8090/foo",
        "http://127.0.0.1:8090/",
        "http://user:password@127.0.0.1:8090",
        "http://127.0.0.1:8090?x=1",
        "http://127.0.0.1:8090#fragment",
        "http://127.0.0.1:8090?",
        "http://127.0.0.1:8090#",
        "http://127.0.0.1:bad",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:08090",
        "http://127.0.0.1:",
        "http://127.0.0.1",
        "https://127.0.0.1:8090",
        "http://127.0.0.2:8090",
        "http://[::1]:8090",
        "http://127.0.0.1:8090\n",
        " http://127.0.0.1:8090",
        "http://127.1:8090",
        "http://2130706433:8090",
        "http://127.0.0.1:8090\\evil",
        "",
    ],
)
def test_invalid_origins(url):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, research_planner_url=url, research_planner_api_key=KEY)
    assert "input_value" not in str(exc.value)
    assert KEY not in str(exc.value)


@pytest.mark.parametrize(
    "key", ["", "x" * 31, "x" * 513, "x" * 32 + "\n", "x" * 32 + " ", "é" * 32]
)
def test_invalid_secret_hidden(key):
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, research_planner_url=URL, research_planner_api_key=key)
    if key:
        assert key not in str(exc.value)


@pytest.mark.parametrize("port", [1, 8090, 65535])
def test_valid_ports(port):
    assert (
        Settings(
            _env_file=None,
            research_planner_url=f"http://127.0.0.1:{port}",
            research_planner_api_key=KEY,
        ).research_planner_url
        == f"http://127.0.0.1:{port}"
    )


async def test_exact_request_and_no_cookie_replay(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9999")
    calls = []
    query = "  " + QUERY + "  "
    fixture = deepcopy(ENVELOPE)
    fixture["plan"]["original_query"] = query
    fixture["timezone"] = "Europe/Copenhagen"

    def handle(request):
        calls.append(request)
        assert request.method == "POST"
        assert str(request.url) == URL + "/plan"
        assert dict(request.headers) == {
            "host": "127.0.0.1:8090",
            "authorization": f"Bearer {KEY}",
            "content-type": "application/json",
            "accept": "application/json",
            "accept-encoding": "identity",
            "content-length": str(len(request.content)),
        }
        assert json.loads(request.content) == {
            "query": query,
            "timezone": "Europe/Copenhagen",
            "language": "auto",
        }
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 30
        )
        return httpx.Response(200, json=fixture, headers={"Set-Cookie": "upstream=secret"})

    planner = ResearchPlannerClient(
        configured(event_timezone="Europe/Copenhagen"), transport=httpx.MockTransport(handle)
    )
    try:
        assert planner._http.trust_env is False
        assert planner._http.follow_redirects is False
        for _ in range(2):
            result = await planner.plan(query)
            assert result.model_dump(mode="json") == fixture
        assert len(calls) == 2
    finally:
        await planner.close()
    assert planner._http.is_closed


@pytest.mark.parametrize("kind", ["plan", "needs_clarification"])
async def test_success_kinds(kind):
    fixture = deepcopy(ENVELOPE)
    fixture["kind"] = kind
    if kind == "needs_clarification":
        fixture["plan"]["clarification"] = "needs_location"
    planner = ResearchPlannerClient(
        configured(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=fixture))
    )
    try:
        assert (await planner.plan(QUERY)).model_dump(mode="json") == fixture
    finally:
        await planner.close()


async def test_explicit_dates_are_parsed_without_string_coercion():
    fixture = deepcopy(ENVELOPE)
    fixture["plan"].update(
        temporal="explicit_range",
        explicit_from_date="2026-10-01",
        explicit_to_date="2026-10-02",
    )
    planner = ResearchPlannerClient(
        configured(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=fixture))
    )
    try:
        assert (await planner.plan(QUERY)).model_dump(mode="json") == fixture
    finally:
        await planner.close()


async def test_stream_limit_stops_reading_and_closes_response():
    class OversizedStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b" " * MAX_RESPONSE_BYTES
            yield b"x"
            pytest.fail("Must stop reading as soon as the response exceeds its limit")

        async def aclose(self):
            self.closed = True

    stream = OversizedStream()
    await assert_rejected(
        httpx.Response(200, stream=stream, headers={"Content-Type": "application/json"})
    )
    assert stream.closed


async def test_compressed_response_rejected_without_reading():
    class UnreadStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail("Must not decompress upstream content")
            yield b""

    await assert_rejected(
        httpx.Response(
            200,
            stream=UnreadStream(),
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
        )
    )


@pytest.mark.parametrize(
    "path,value",
    [
        ("schema_version", "research-query-plan-v1"),
        ("schema_version", "research-query-plan-v2"),
        ("schema_version", "research-query-plan-v4"),
        ("prompt_version", "research-planner-v4"),
        ("prompt_version", "research-planner-v5"),
        ("prompt_version", "research-planner-v6"),
        ("prompt_version", "research-planner-v8"),
        ("kind", "other"),
        ("kind", "needs_clarification"),
        ("extra", "secret"),
        ("plan.extra", "secret"),
        ("diagnostics.extra", "secret"),
        ("plan.intent", "invented"),
        ("plan.entity_type", "user"),
        ("plan.requires_semantic_relevance", "true"),
        ("plan.category_queries", "music"),
        ("plan.category_queries", ["x"] * 9),
        ("plan.area_query", "x" * 161),
        ("plan.semantic_query", "x" * 501),
        ("plan.semantic_query", " "),
        ("plan.original_query", "mismatch"),
        ("timezone", "UTC"),
        ("plan.answer_mode", "records"),
        ("plan.unsupported_reason", "multi_area"),
        ("plan.explicit_from_date", "2026-09-01"),
        ("diagnostics.planner_prompt_version", "research-planner-v3"),
        ("diagnostics.planner_intent", "list"),
        ("diagnostics.planner_model", "different"),
        ("diagnostics.planner_ms", -1),
        ("diagnostics.total_ms", float("inf")),
        ("diagnostics.request_id", "not-a-request-id"),
        ("reference_date", 123),
        ("reference_date", "2026-99-99"),
    ],
)
async def test_invalid_response_contract(path, value):
    fixture = deepcopy(ENVELOPE)
    target = fixture
    parts = path.split(".")
    for key in parts[:-1]:
        target = target[key]
    target[parts[-1]] = value
    await assert_rejected(
        httpx.Response(
            200, content=json.dumps(fixture), headers={"Content-Type": "application/json"}
        )
    )


@pytest.mark.parametrize("field", list(ENVELOPE))
async def test_all_envelope_fields_required(field):
    fixture = deepcopy(ENVELOPE)
    del fixture[field]
    await assert_rejected(httpx.Response(200, json=fixture))


@pytest.mark.parametrize("field", list(ENVELOPE["plan"]))
async def test_nullable_plan_fields_still_required(field):
    fixture = deepcopy(ENVELOPE)
    del fixture["plan"][field]
    await assert_rejected(httpx.Response(200, json=fixture))


async def assert_rejected(response, status=502, code="research_planner_invalid_response"):
    calls = []

    def handle(request):
        calls.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    planner = ResearchPlannerClient(configured(), transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(APIError) as exc:
            await planner.plan(QUERY)
        assert (exc.value.status, exc.value.code) == (status, code)
        assert "upstream-private" not in exc.value.message
        assert QUERY not in exc.value.message
        assert len(calls) == 1  # No retries, including redirects and transient failures.
        if isinstance(response, httpx.Response):
            assert response.is_closed
    finally:
        await planner.close()


@pytest.mark.parametrize(
    "status,upstream_code,expected,code",
    [
        (422, "planner_unsupported_plan", 422, "research_plan_unsupported"),
        (422, "invalid_request", 502, "research_planner_invalid_response"),
        (422, "unknown", 502, "research_planner_invalid_response"),
        (502, "planner_invalid_response", 502, "research_planner_invalid_response"),
        (503, "planner_unavailable", 503, "research_planner_unavailable"),
        (401, "unauthorized", 503, "research_planner_unavailable"),
        (403, "unauthorized", 503, "research_planner_unavailable"),
        (500, "private", 502, "research_planner_invalid_response"),
        (504, "private", 502, "research_planner_invalid_response"),
        (429, "private", 502, "research_planner_invalid_response"),
        (201, "private", 502, "research_planner_invalid_response"),
        (204, "private", 502, "research_planner_invalid_response"),
        (302, "private", 502, "research_planner_invalid_response"),
        (307, "private", 502, "research_planner_invalid_response"),
    ],
)
async def test_safe_error_mapping(status, upstream_code, expected, code):
    await assert_rejected(
        httpx.Response(
            status,
            json={"error": {"code": upstream_code, "message": "upstream-private"}},
            headers={"Location": "https://external.invalid"},
        ),
        expected,
        code,
    )


@pytest.mark.parametrize("status", [200, 422])
@pytest.mark.parametrize(
    "body,media",
    [
        (b"{", "application/json"),
        (b"<html>upstream-private</html>", "text/html"),
        (b"null", "application/json"),
        (b"[]", "application/json"),
        (b"\xff", "application/json"),
        (b"x" * (MAX_RESPONSE_BYTES + 1), "application/json"),
    ],
)
async def test_malformed_or_oversized(status, body, media):
    await assert_rejected(httpx.Response(status, content=body, headers={"Content-Type": media}))


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError]
)
async def test_transport_failure(error):
    await assert_rejected(error("upstream-private"), 503, "research_planner_unavailable")


async def test_total_deadline():
    async def slow(request):
        await asyncio.sleep(2)
        return httpx.Response(200, json=ENVELOPE)

    planner = ResearchPlannerClient(
        configured(research_planner_timeout_seconds=1), transport=httpx.MockTransport(slow)
    )
    try:
        with pytest.raises(APIError) as exc:
            await planner.plan(QUERY)
        assert exc.value.code == "research_planner_unavailable"
    finally:
        await planner.close()


@pytest.fixture
async def api_planner(client):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=ENVELOPE)

    planner = ResearchPlannerClient(configured(), transport=httpx.MockTransport(handle))
    client._transport.app.state.research_planner = planner
    try:
        yield requests
    finally:
        await planner.close()


async def test_anonymous_and_unconfigured(client, headers):
    assert (await client.post(PATH, json={"query": QUERY})).status_code == 401
    response = await client.post(PATH, headers=headers, json={"query": QUERY})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "research_planner_unavailable"
    assert (await client.get("/health")).status_code == 200


@pytest.mark.parametrize(
    "admin,journalist,status", [(False, False, 403), (False, True, 200), (True, False, 200)]
)
async def test_research_authorization(client, api_planner, admin, journalist, status):
    client._transport.app.dependency_overrides[get_identity] = lambda: AdminPrincipal(
        subject="admin:test", system_admin=admin, journalist=journalist
    )
    response = await client.post(
        PATH,
        json={"query": QUERY},
        headers={
            "Authorization": "Bearer browser-value",
            "Cookie": "browser=secret",
            "X-Admin-CSRF": "1",
            "X-Real-IP": "192.0.2.1",
            "X-Custom": "private",
        },
    )
    assert response.status_code == status
    assert len(api_planner) == (1 if status == 200 else 0)
    if status == 200:
        assert response.json() == ENVELOPE
        assert response.headers["cache-control"] == "private, no-store"
        sent = api_planner[0]
        assert sent.headers["Authorization"] == f"Bearer {KEY}"
        for header in ("Cookie", "X-Admin-CSRF", "X-Real-IP", "X-Custom"):
            assert header not in sent.headers


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"query": ""},
        {"query": "  \n\t"},
        {"query": "x" * 2001},
        {"query": 123},
        *(
            {"query": QUERY, field: "browser-controlled"}
            for field in (
                "timezone",
                "language",
                "model",
                "provider",
                "url",
                "api_key",
                "prompt_version",
                "schema_version",
                "timeout",
            )
        ),
    ],
)
async def test_request_validation(client, headers, api_planner, body):
    response = await client.post(PATH, headers=headers, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert not api_planner
    assert "browser-controlled" not in response.text


def test_request_text_preserved_and_length_boundary():
    for query in (" x ", "x", "😀" * 2000):
        assert ResearchPlanRequest(query=query).query == query


async def test_lone_unicode_surrogate_rejected(client, headers, api_planner):
    response = await client.post(
        PATH,
        headers={**headers, "Content-Type": "application/json"},
        content=b'{"query":"private \\ud800"}',
    )
    assert response.status_code == 422
    assert "private" not in response.text
    assert not api_planner


async def test_chunked_body_limit(client, headers, api_planner):
    async def chunks():
        for _ in range(5):
            yield b" " * 8192

    response = await client.post(
        PATH, headers={**headers, "Content-Type": "application/json"}, content=chunks()
    )
    assert response.status_code == 413
    assert not api_planner


@pytest.mark.parametrize(
    "csrf",
    [
        {},
        {"Origin": "https://admin.test"},
        {"X-Admin-CSRF": "1"},
        {"Origin": "https://evil.test", "X-Admin-CSRF": "1"},
        {"Origin": "https://admin.test", "X-Admin-CSRF": "1"},
    ],
)
async def test_real_cookie_csrf_dependency(client, api_planner, monkeypatch, csrf):
    app = client._transport.app
    app.state.settings.auth_public_origin = "https://admin.test"

    async def identity(*args):
        return AdminPrincipal(subject="admin:test", journalist=True)

    monkeypatch.setattr("app.auth.dependencies.session_identity", identity)
    client.cookies.set("admin_session", "a" * 43)
    response = await client.post(PATH, json={"query": QUERY}, headers=csrf)
    allowed = csrf == {"Origin": "https://admin.test", "X-Admin-CSRF": "1"}
    assert response.status_code == (200 if allowed else 403)
    assert len(api_planner) == int(allowed)


async def test_lifecycle_no_startup_network_and_close(monkeypatch):
    created = []
    original = httpx.AsyncClient

    def factory(**kwargs):
        def never(request):
            pytest.fail("Startup/health must not call planner")

        client = original(**kwargs, transport=httpx.MockTransport(never))
        created.append(client)
        return client

    # Production construction passes transport=None; replace it only for this test.
    def configured_factory(**kwargs):
        kwargs.pop("transport", None)
        return factory(**kwargs)

    monkeypatch.setattr("app.services.research_planner.httpx.AsyncClient", configured_factory)
    app = create_app(configured())
    async with app.router.lifespan_context(app):
        assert len(created) == 1
        assert not created[0].is_closed
    assert created[0].is_closed


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json=ENVELOPE),
        httpx.Response(
            200, content="query private invalid", headers={"Content-Type": "application/json"}
        ),
        httpx.ReadTimeout("upstream-private " + KEY + QUERY),
    ],
)
async def test_query_privacy_including_debug_logs(client, headers, caplog, response):
    # Capture the actual formatter with debug tracebacks enabled as well as raw records.
    logger = logging.getLogger("admin")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.DEBUG)
    client._transport.app.state.settings.app_debug = True
    private = [
        QUERY,
        KEY,
        "kulturell interessant",
        "Flensburg",
        "upstream-private",
        "original_query",
    ]

    def handle(request):
        if isinstance(response, Exception):
            raise response
        return response

    planner = ResearchPlannerClient(configured(), transport=httpx.MockTransport(handle))
    client._transport.app.state.research_planner = planner
    try:
        result = await client.post(PATH, headers=headers, json={"query": QUERY})
        assert result.status_code in {200, 502, 503}
        formatter = JsonFormatter(debug=True)
        formatted = "\n".join(formatter.format(record) for record in caplog.records)
        assert "research_planner_request" in formatted
        for value in private:
            assert value not in formatted
            assert value not in caplog.text
        if result.status_code != 200:
            for value in private:
                assert value not in result.text
    finally:
        logger.removeHandler(caplog.handler)
        await planner.close()
