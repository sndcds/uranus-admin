"""Bounded server-to-server language planning. No retrieval, persistence or retries."""

import asyncio
import json
import logging
from time import perf_counter
from typing import Literal

import httpx
from pydantic import TypeAdapter, ValidationError

from app.config import Settings
from app.errors import APIError
from app.research.wire.research_v8_schema import PlanResponseV8
from app.research.wire.research_v9_schema import PlanResponseV9
from app.research.wire.research_v10_schema import PlanResponseV10
from app.research.wire.research_v11_schema import PlanResponseV11
from app.schemas.research_analytics import AnalyticalPlanResponse
from app.schemas.research_conversation import ResearchConversationContext
from app.schemas.research_geography import GeographicPlanResponse
from app.schemas.research_planner import PlanResponse

MAX_RESPONSE_BYTES = 32 * 1024
PLAN_RESPONSE: TypeAdapter[PlanResponse] = TypeAdapter(PlanResponse)


def unavailable() -> APIError:
    return APIError(503, "research_planner_unavailable", "Research planner unavailable.")


def invalid_response() -> APIError:
    return APIError(502, "research_planner_invalid_response", "Research planner response invalid.")


class ResearchPlannerClient:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if settings.research_planner_url is None or settings.research_planner_api_key is None:
            raise ValueError("Research planner configuration required")
        self._url = settings.research_planner_url + "/plan"
        self._key = settings.research_planner_api_key
        self._timezone = settings.event_timezone
        self._timeout = settings.research_planner_timeout_seconds
        self._http = httpx.AsyncClient(
            timeout=self._timeout,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def plan(
        self, query: str, *, analytical: bool = False, geographic: bool = False
    ) -> PlanResponse | AnalyticalPlanResponse | GeographicPlanResponse:
        started = perf_counter()
        status = 200
        error_code = "none"
        try:
            # Total deadline also bounds slow streaming; httpx bounds each network operation.
            async with asyncio.timeout(self._timeout):
                return await self._plan(query, analytical=analytical, geographic=geographic)
        except (httpx.RequestError, TimeoutError):
            status, error_code = 503, "research_planner_unavailable"
            raise unavailable() from None
        except APIError as exc:
            status, error_code = exc.status, exc.code
            raise
        finally:
            logging.getLogger("admin.research_planner").info(
                "research_planner_request",
                extra={
                    "status_code": status,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "error_type": error_code,
                },
            )

    async def _plan(
        self, query: str, *, analytical: bool = False, geographic: bool = False
    ) -> PlanResponse | AnalyticalPlanResponse | GeographicPlanResponse:
        # Construct independently of inbound requests AND the client's cookie jar.
        # Even a planner Set-Cookie response must never be sent on the next request.
        request = httpx.Request(
            "POST",
            self._url.removesuffix("/plan") + "/v6/plan"
            if geographic
            else self._url.removesuffix("/plan") + "/v5/plan"
            if analytical
            else self._url,
            headers={
                "Authorization": f"Bearer {self._key.get_secret_value()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            json={"query": query, "timezone": self._timezone, "language": "auto"},
        )
        response = await self._http.send(request, stream=True)
        try:
            if response.status_code in {401, 403, 503}:
                raise unavailable()
            if response.status_code not in {200, 422}:
                raise invalid_response()
            if (
                response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise invalid_response()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise invalid_response()
                body.extend(chunk)
            if response.status_code == 422:
                # Only the documented unsupported error is a user-facing 422.
                # Never reflect the upstream message or any other provider content.
                try:
                    error = json.loads(body)
                except (ValueError, RecursionError):
                    raise invalid_response() from None
                if (
                    isinstance(error, dict)
                    and isinstance(error.get("error"), dict)
                    and error["error"].get("code") == "planner_unsupported_plan"
                ):
                    raise APIError(
                        422, "research_plan_unsupported", "This research request is unsupported."
                    )
                raise invalid_response()
            try:
                envelope = (
                    TypeAdapter(GeographicPlanResponse).validate_json(body)
                    if geographic
                    else TypeAdapter(AnalyticalPlanResponse).validate_json(body)
                    if analytical
                    else PLAN_RESPONSE.validate_json(body)
                )
            except ValidationError:
                raise invalid_response() from None
            if (
                envelope.plan.original_query != query
                or envelope.timezone != self._timezone
                or envelope.plan.unsupported_reason is not None
                or (envelope.kind == "plan") != (envelope.plan.clarification == "none")
                or envelope.diagnostics.planner_intent != envelope.plan.intent
                or envelope.diagnostics.planner_model != envelope.model
                or envelope.diagnostics.planner_prompt_version != envelope.prompt_version
            ):
                raise invalid_response()
            return envelope
        finally:
            await response.aclose()

    async def plan_administrative(self, query: str) -> "PlanResponseV8":
        """One bounded v8 request. No retry, old-contract fallback or provider reflection."""
        try:
            async with asyncio.timeout(self._timeout):
                request = httpx.Request(
                    "POST",
                    self._url.removesuffix("/plan") + "/v8/plan",
                    headers={
                        "Authorization": f"Bearer {self._key.get_secret_value()}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    json={"query": query, "timezone": self._timezone, "language": "auto"},
                )
                response = await self._http.send(request, stream=True)
                try:
                    if response.status_code in {401, 403, 503}:
                        raise unavailable()
                    if (
                        response.status_code != 200
                        or response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise invalid_response()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise invalid_response()
                        body.extend(chunk)
                    envelope = PlanResponseV8.model_validate_json(body)
                    if (
                        envelope.plan.original_query != query
                        or envelope.timezone != self._timezone
                        or envelope.diagnostics.planner_model != envelope.model
                        or envelope.diagnostics.planner_prompt_version != envelope.prompt_version
                    ):
                        raise invalid_response()
                    return envelope
                finally:
                    await response.aclose()
        except (httpx.HTTPError, TimeoutError):
            raise unavailable() from None
        except ValueError:
            raise invalid_response() from None

    async def plan_grouped(self, query: str) -> "PlanResponseV9":
        return await self._plan_language(query, "v9", PlanResponseV9)

    async def plan_calendar(self, query: str) -> PlanResponseV10:
        return await self._plan_language(query, "v10", PlanResponseV10)

    async def plan_conversation(
        self, query: str, context: ResearchConversationContext | None = None
    ) -> PlanResponseV11:
        return await self._plan_language(query, "v11", PlanResponseV11, context)

    async def _plan_language[T: (PlanResponseV9, PlanResponseV10, PlanResponseV11)](
        self,
        query: str,
        version: Literal["v9", "v10", "v11"],
        model: type[T],
        context: ResearchConversationContext | None = None,
    ) -> T:
        """One bounded request; closed transport choice, no retry or fallback."""
        try:
            async with asyncio.timeout(self._timeout):
                request = httpx.Request(
                    "POST",
                    self._url.removesuffix("/plan") + f"/{version}/plan",
                    headers={
                        "Authorization": f"Bearer {self._key.get_secret_value()}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    json={
                        "query": query,
                        "timezone": self._timezone,
                        "language": "auto",
                        **(
                            {"conversation_context": context.model_dump(mode="json")}
                            if context is not None
                            else {}
                        ),
                    },
                )
                response = await self._http.send(request, stream=True)
                try:
                    if response.status_code in {401, 403, 503}:
                        raise unavailable()
                    if (
                        response.status_code != 200
                        or response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity") != "identity"
                    ):
                        raise invalid_response()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise invalid_response()
                        body.extend(chunk)
                    envelope = model.model_validate_json(body)
                    if (
                        envelope.plan.original_query != query
                        or envelope.timezone != self._timezone
                        or envelope.diagnostics.planner_model != envelope.model
                        or envelope.diagnostics.planner_prompt_version != envelope.prompt_version
                    ):
                        raise invalid_response()
                    return envelope
                finally:
                    await response.aclose()
        except (httpx.HTTPError, TimeoutError):
            raise unavailable() from None
        except ValueError:
            raise invalid_response() from None


async def plan_active(
    planner: ResearchPlannerClient,
    settings: Settings,
    query: str,
    context: ResearchConversationContext | None = None,
) -> (
    PlanResponse
    | AnalyticalPlanResponse
    | GeographicPlanResponse
    | PlanResponseV9
    | PlanResponseV10
    | PlanResponseV11
):
    """Select the configured wire contract once; never retry on an older contract."""
    if context is not None and settings.research_planner_contract != "v11":
        raise APIError(
            422, "research_execution_unsupported", "Conversation planning is not enabled."
        )
    if settings.research_planner_contract in {"v9", "v10", "v11"}:
        response = (
            await planner.plan_conversation(query, context)
            if settings.research_planner_contract == "v11"
            else await planner.plan_calendar(query)
            if settings.research_planner_contract == "v10"
            else await planner.plan_grouped(query)
        )
        # Revalidate injected clients too: model_copy/construct bypass validators.
        try:
            response = (
                PlanResponseV11
                if settings.research_planner_contract == "v11"
                else PlanResponseV10
                if settings.research_planner_contract == "v10"
                else PlanResponseV9
            ).model_validate_json(response.model_dump_json())
            if (
                response.plan.original_query != query
                or response.timezone != settings.event_timezone
                or response.diagnostics.planner_model != response.model
                or response.diagnostics.planner_prompt_version != response.prompt_version
            ):
                raise ValueError("planner_identity_mismatch")
        except ValueError:
            raise invalid_response() from None
        return response
    if settings.research_geocoder_api_key:
        return await planner.plan(query, geographic=True)
    if settings.research_analytics_enabled:
        return await planner.plan(query, analytical=True)
    return await planner.plan(query)
