"""Fixed server-to-server v4 routes; no browser credentials or routing selectors."""

import asyncio

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.errors import APIError
from app.schemas.project_knowledge import AnswerResponse
from app.schemas.research_domain import KnowledgePlan, PlanEnvelopeV4


class ResearchDomainClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.http = httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=settings.research_planner_timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, path: str, body: dict[str, str], *, knowledge: bool = False) -> bytes:
        url = (
            self.settings.research_knowledge_url
            if knowledge
            else self.settings.research_planner_url
        )
        key = (
            self.settings.research_knowledge_api_key
            if knowledge
            else self.settings.research_planner_api_key
        )
        if url is None or key is None:
            raise APIError(503, "research_domain_unavailable", "Research service unavailable.")
        request = httpx.Request(
            "POST",
            url + path,
            json=body,
            headers={
                "Authorization": "Bearer " + key.get_secret_value(),
                "Accept-Encoding": "identity",
                "Accept": "application/json",
            },
        )
        try:
            async with asyncio.timeout(self.settings.research_planner_timeout_seconds):
                response = await self.http.send(request, stream=True)
                try:
                    if response.status_code == 422 and not knowledge:
                        raise APIError(
                            422, "research_plan_unsupported", "This question is unsupported."
                        )
                    if response.status_code == 502 and not knowledge:
                        raise APIError(502, "research_domain_invalid", "Invalid research plan.")
                    if response.status_code != 200:
                        raise APIError(
                            503, "research_domain_unavailable", "Research service unavailable."
                        )
                    if (
                        response.headers.get("content-type", "").split(";")[0] != "application/json"
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise ValueError
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > (256 * 1024 if knowledge else 16 * 1024):
                            raise ValueError
                    return bytes(data)
                finally:
                    await response.aclose()
        except (httpx.HTTPError, TimeoutError):
            raise APIError(
                503, "research_domain_unavailable", "Research service unavailable."
            ) from None
        except ValueError:
            raise APIError(
                502, "research_domain_invalid", "Invalid research service response."
            ) from None

    async def plan(self, query: str) -> PlanEnvelopeV4:
        data = await self.request("/v4/plan", {"query": query})
        try:
            result = PlanEnvelopeV4.model_validate_json(data)
            if result.original_query != query:
                raise ValueError
            if isinstance(result.plan, KnowledgePlan) and result.plan.knowledge_query != query:
                raise ValueError
            return result
        except (ValidationError, ValueError):
            raise APIError(502, "research_domain_invalid", "Invalid research plan.") from None

    async def answer(self, plan: KnowledgePlan) -> AnswerResponse:
        data = await self.request(
            "/evidence-answer", {"query": plan.knowledge_query, "fact": plan.fact}, knowledge=True
        )
        try:
            result = AnswerResponse.model_validate_json(data)
            if any(f.key != plan.fact for f in result.facts):
                raise ValueError
            return result
        except (ValidationError, ValueError):
            raise APIError(502, "research_domain_invalid", "Invalid evidence response.") from None
