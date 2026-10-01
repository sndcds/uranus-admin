"""Planner PR #12 public contract; no provider internals or live service calls."""

import itertools
import json
from pathlib import Path
from typing import get_args

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.errors import APIError
from app.schemas.research_domain import DataPlan, FactKey, KnowledgePlan, PlanEnvelopeV4
from app.services.research_domain_client import ResearchDomainClient

FACTS = (
    "uranus_overview",
    "admin_overview",
    "semantic_search_repository",
    "embedding_component",
    "embedding_model",
    "qdrant_usage",
    "encoder_communication",
    "planner_component",
    "geocoding",
    "architecture",
    "founding_date",
)
PAIRS = {
    ("event", "description_characters"),
    ("event", "occurrence_count"),
    ("organization", "event_count"),
    ("organization", "venue_count"),
    ("venue", "occurrence_count"),
    ("category", "event_count"),
}
QUESTION = "  Welche Komponente erzeugt die Embeddings?\n"


def envelope(plan=None, **updates):
    return {
        "schema_version": "research-query-plan-v4",
        "interpreter_version": "research-domain-planner-v2",
        "original_query": QUESTION,
        "plan": plan
        if plan is not None
        else {
            "domain": "project_knowledge",
            "operation": "evidence_answer",
            "knowledge_query": QUESTION,
            "fact": "embedding_component",
            "answer_mode": "evidence",
        },
        **updates,
    }


def test_public_schema_matches_pinned_planner():
    fixture = json.loads(Path("tests/fixtures/research_domain_planner_schema.json").read_text())
    assert fixture["commit"] == "48831449947520ce3a42c465d0e0357c4316c823"
    assert PlanEnvelopeV4.model_json_schema() == fixture["schema"]
    assert get_args(FactKey) == FACTS


@pytest.mark.parametrize(
    "entity,metric",
    list(
        itertools.product(
            ("event", "venue", "organization", "category"),
            ("description_characters", "occurrence_count", "event_count", "venue_count"),
        )
    ),
)
def test_exact_pair_matrix(entity, metric):
    if (entity, metric) in PAIRS:
        plan = DataPlan(entity_type=entity, metric=metric)
        assert (plan.ordering, plan.limit) == ("desc", 1)
    else:
        with pytest.raises(ValidationError):
            DataPlan(entity_type=entity, metric=metric)


@pytest.mark.parametrize("fact", FACTS)
def test_all_reviewed_facts_preserve_question(fact):
    plan = KnowledgePlan(fact=fact, knowledge_query=QUESTION)
    assert plan.knowledge_query == QUESTION


@pytest.mark.parametrize("entity,metric", sorted(PAIRS))
def test_area_pair_matrix(entity, metric):
    values = {"entity_type": entity, "metric": metric, "area_query": "Flensburg"}
    if (entity, metric) == ("organization", "event_count"):
        assert DataPlan.model_validate(values).area_query == "Flensburg"
    else:
        with pytest.raises(ValidationError):
            DataPlan.model_validate(values)


INVALID_DATA = [
    {"entity_type": "area", "metric": "event_count"},
    *(
        {"entity_type": "event", "metric": metric}
        for metric in (
            "description_words",
            "public_text_characters",
            "duration_minutes",
            "organization_count",
            "category_count",
            "area_count",
            "events_per_capita",
        )
    ),
    {"entity_type": "event", "metric": "event_count"},
    {"entity_type": "venue", "metric": "event_count"},
    {"entity_type": "category", "metric": "occurrence_count"},
    *(
        {"entity_type": entity, "metric": metric, "area_query": "Flensburg"}
        for entity, metric in sorted(PAIRS - {("organization", "event_count")})
    ),
    *(
        {"entity_type": "organization", "metric": "event_count", "area_query": area}
        for area in ("", " \t", "x" * 161)
    ),
    *(
        {"entity_type": "event", "metric": "occurrence_count", "limit": limit}
        for limit in (0, 21, True, "1")
    ),
    {"entity_type": "event", "metric": "occurrence_count", "ordering": "random()"},
]
INVALID_ENVELOPES = [
    *(envelope({"domain": "data", **data}) for data in INVALID_DATA),
    envelope(interpreter_version="reviewed-catalogue-v1"),
    envelope(schema_version="research-query-plan-v3"),
    envelope(original_query="changed"),
    envelope(plan={"domain": "project_knowledge", "fact": "unknown", "knowledge_query": QUESTION}),
    *(
        envelope(
            plan={
                "domain": "project_knowledge",
                "fact": "embedding_component",
                "knowledge_query": text,
            }
        )
        for text in (
            "",
            " \n\t",
            "x" * 2001,
            QUESTION.strip(),
            QUESTION.casefold(),
            " ".join(QUESTION.split()),
            "Jina embedding model",
            "uranus-admin semantic search",
            "sndcds/uranus-admin",
        )
    ),
    {**envelope(), "plan": None},
    envelope(facts=["invented"]),
]


@pytest.fixture
def domain_settings(settings):
    settings.research_planner_url = "http://127.0.0.1:8090"
    settings.research_planner_api_key = SecretStr("synthetic-planner-key-32-characters")
    return settings


@pytest.mark.parametrize("wire", INVALID_ENVELOPES)
async def test_client_rejects_invalid_public_plan(domain_settings, wire):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=wire)

    client = ResearchDomainClient(domain_settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as exc:
            await client.plan(QUESTION)
        assert (exc.value.status, exc.value.code) == (502, "research_domain_invalid")
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize(
    "status,expected_status,code",
    [
        (422, 422, "research_plan_unsupported"),
        (502, 502, "research_domain_invalid"),
        (503, 503, "research_domain_unavailable"),
        (302, 503, "research_domain_unavailable"),
    ],
)
async def test_planner_status_mapping_without_body_or_retry(
    domain_settings, status, expected_status, code, caplog
):
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == "http://127.0.0.1:8090/v4/plan"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer synthetic-planner-key-32-characters"
        assert json.loads(request.content) == {"query": QUESTION}
        return httpx.Response(
            status, text="private-provider-response", headers={"Location": "http://other.invalid"}
        )

    client = ResearchDomainClient(domain_settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as exc:
            await client.plan(QUESTION)
        assert (exc.value.status, exc.value.code) == (expected_status, code)
        assert "private-provider-response" not in str(exc.value) + caplog.text
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError, TimeoutError])
async def test_planner_transport_errors_are_unavailable(domain_settings, error):
    calls = []

    def handler(request):
        calls.append(request)
        raise error("private-transport-details")

    client = ResearchDomainClient(domain_settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as exc:
            await client.plan(QUESTION)
        assert (exc.value.status, exc.value.code) == (503, "research_domain_unavailable")
        assert "private-transport-details" not in str(exc.value)
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize(
    "body,headers",
    [
        (b"not-json", {"content-type": "application/json"}),
        (b"{}", {"content-type": "text/plain"}),
        (b"x" * (16 * 1024 + 1), {"content-type": "application/json"}),
    ],
)
async def test_invalid_planner_response_is_not_repaired(domain_settings, body, headers):
    client = ResearchDomainClient(
        domain_settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body, headers=headers)
        ),
    )
    try:
        with pytest.raises(APIError) as exc:
            await client.plan(QUESTION)
        assert (exc.value.status, exc.value.code) == (502, "research_domain_invalid")
    finally:
        await client.close()
