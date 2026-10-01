"""Deterministic execution of validated server-side plans. No inference or persistence."""

import asyncio
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from time import perf_counter
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.research import research_page
from app.repositories.research_execution import (
    aggregate_selection,
    chronological_records,
    count_selection,
    eligible_event_ids,
)
from app.repositories.research_resolution import Resolution, resolve_plan
from app.schemas.research_execution import (
    AggregateResult,
    ComparisonItem,
    ComparisonResult,
    CountResult,
    ExecutionClarification,
    ExecutionDiagnostics,
    ExecutionFilters,
    ExecutionGrouping,
    ExecutionMetric,
    ExecutionProvenance,
    ExecutionResult,
    ExecutionSemanticFilters,
    RecordsResult,
    ResearchExecutionResponse,
)
from app.schemas.research_planner import PlanResponse
from app.services.semantic_search import semantic_research

EVENING_START = time(18)


def unsupported(message: str) -> APIError:
    return APIError(
        422,
        "research_execution_unsupported",
        message,
    )


def temporal_bounds(response: PlanResponse) -> tuple[date | None, date | None]:
    # reference_date is already a local date in this validated zone. Calendar
    # arithmetic deliberately avoids UTC offsets, including across DST changes.
    ZoneInfo(response.timezone)
    ref, plan = response.reference_date, response.plan
    monday = ref - timedelta(days=ref.weekday())
    match plan.temporal:
        case "none":
            return None, None
        case "today":
            return ref, ref
        case "tomorrow":
            tomorrow = ref + timedelta(days=1)
            return tomorrow, tomorrow
        case "this_weekend":
            return monday + timedelta(days=5), monday + timedelta(days=6)
        case "next_week":
            return monday + timedelta(days=7), monday + timedelta(days=13)
        case "this_month":
            return ref.replace(day=1), ref.replace(day=monthrange(ref.year, ref.month)[1])
        case "this_year":
            return ref.replace(month=1, day=1), ref.replace(month=12, day=31)
        case "past":
            return None, ref - timedelta(days=1)
        case "future":
            return ref, None
        case "explicit_range":
            return plan.explicit_from_date, plan.explicit_to_date


def execution_filters(response: PlanResponse, resolution: Resolution) -> ExecutionFilters:
    start, end = temporal_bounds(response)
    filters = ExecutionFilters(
        entity_type=response.plan.entity_type,
        from_date=start,
        to_date=end,
        time_from=EVENING_START if response.plan.time_of_day == "evening" else None,
        page_size=response.plan.limit or 20,
        area_id=resolution.area.area.id if resolution.area else None,
    )
    for item in resolution.fields:
        if item.field == "venue_query":
            filters.venue_id = UUID(item.target.id)
        elif item.field == "organization_query":
            filters.organization_id = UUID(item.target.id)
        elif item.field == "event_type_queries":
            filters.event_type_ids.append(int(item.target.id))
        elif item.field == "category_queries":
            filters.category_ids.append(int(item.target.id))
        elif item.field == "genre_queries":
            filters.genre_keys.append(item.target.id)
    filters.event_type_ids = sorted(set(filters.event_type_ids))
    filters.category_ids = sorted(set(filters.category_ids))
    filters.genre_keys = sorted(set(filters.genre_keys))
    return filters


class ResearchPlanExecutor:
    async def execute(
        self,
        request: Request,
        settings: Settings,
        plan_response: PlanResponse,
        *,
        planner_ms: float | None = None,
    ) -> ResearchExecutionResponse:
        started = perf_counter()
        planner_ms = plan_response.diagnostics.total_ms if planner_ms is None else planner_ms
        plan = plan_response.plan
        resolution = Resolution()
        provenance = ExecutionProvenance()
        resolution_ms = execution_ms = 0.0
        observed_at = datetime.now(UTC)
        if plan.unsupported_reason is not None:
            raise APIError(422, "research_plan_unsupported", "This research plan is unsupported.")
        if plan_response.kind == "needs_clarification":
            result: ExecutionResult = ExecutionClarification(
                reason="planner", planner_state=plan.clarification
            )
        else:
            if plan.clarification != "none" or plan_response.timezone != settings.event_timezone:
                raise APIError(
                    502, "research_execution_invalid_plan", "The research plan is invalid."
                )
            if plan.requires_semantic_relevance and plan.entity_type != "event":
                raise unsupported("Semantic execution is supported only for events.")
            if plan.requires_semantic_relevance and plan.intent in {
                "count",
                "aggregate",
                "compare",
            }:
                raise unsupported(
                    "Exact semantic counts, aggregates and comparisons are not supported."
                )
            if plan.group_by == "area":
                raise unsupported("Area grouping requires an explicit non-overlapping area level.")
            # A comparison target intersects all common filters. Overriding a
            # common constraint of the same dimension would broaden the query.
            if any(
                (t.kind == "area" and plan.area_query)
                or (t.kind == "venue" and plan.venue_query)
                or (t.kind == "organization" and plan.organization_query)
                for t in plan.comparison_targets
            ):
                raise unsupported(
                    "Comparison targets cannot replace a common filter of the same type."
                )
            try:
                # Bound the complete resolution stage, in addition to DB statement limits.
                async with asyncio.timeout(settings.db_timeout_seconds):
                    resolution = await resolve_plan(request, settings, plan)
                resolution_ms = (perf_counter() - started) * 1000
                if resolution.clarification is not None:
                    result = resolution.clarification
                else:
                    filters = execution_filters(plan_response, resolution)
                    provenance = ExecutionProvenance(
                        from_date=filters.from_date,
                        to_date=filters.to_date,
                        time_from=filters.time_from,
                        event_type_ids=filters.event_type_ids,
                        category_ids=filters.category_ids,
                        genre_keys=filters.genre_keys,
                        structured=True,
                        semantic=plan.requires_semantic_relevance,
                    )
                    before = perf_counter()
                    if plan.requires_semantic_relevance:
                        assert plan.semantic_query is not None
                        semantic_filters = ExecutionSemanticFilters(
                            **{
                                k: v
                                for k, v in filters.model_dump().items()
                                if k not in {"q", "sort"}
                            },
                            q="\n".join(
                                dict.fromkeys(
                                    term
                                    for term in (plan.semantic_query, plan.semantic_focus)
                                    if term
                                )
                            ),
                        )
                        # Complete UUID-only eligibility in a short read-only snapshot.
                        # Release it before embedding/ranking; final rehydration checks
                        # the same constraints again in a fresh authoritative snapshot.
                        async with (
                            asyncio.timeout(settings.db_timeout_seconds),
                            asynccontextmanager(get_connection)(request) as connection,
                        ):
                            eligible_ids = await eligible_event_ids(
                                connection, settings, filters, resolution.area
                            )
                        page = await semantic_research(
                            request,
                            settings,
                            semantic_filters,
                            eligible_ids=eligible_ids,
                            resolved_area=resolution.area,
                        )
                        result = RecordsResult(items=list(page.items))
                        observed_at = page.observed_at
                    else:
                        # No planner/embedding/vector work holds this source snapshot.
                        async with (
                            asyncio.timeout(settings.db_timeout_seconds),
                            asynccontextmanager(get_connection)(request) as connection,
                        ):
                            observed_at = datetime.now(UTC)
                            if plan.intent == "count":
                                metric = cast(ExecutionMetric, plan.metric)
                                result = CountResult(
                                    metric=metric,
                                    value=await count_selection(
                                        connection, settings, filters, metric, resolution.area
                                    ),
                                )
                            elif plan.intent == "aggregate":
                                metric = cast(ExecutionMetric, plan.metric)
                                grouping = cast(ExecutionGrouping, plan.group_by)
                                result = AggregateResult(
                                    metric=metric,
                                    group_by=grouping,
                                    items=await aggregate_selection(
                                        connection,
                                        settings,
                                        filters,
                                        metric,
                                        grouping,
                                        resolution.area,
                                    ),
                                )
                            elif plan.intent == "compare":
                                metric = cast(ExecutionMetric, plan.metric)
                                comparisons = []
                                for target in plan.comparison_targets:
                                    selected = next(
                                        r.target
                                        for r in resolution.fields
                                        if r.field == "comparison_targets"
                                        and r.query == target.query
                                        and r.target.entity_type == target.kind
                                    )
                                    target_filters = filters.model_copy(deep=True)
                                    area = resolution.area
                                    if target.kind == "area":
                                        area = resolution.target_areas[selected.id]
                                        target_filters.area_id = area.area.id
                                    elif target.kind == "venue":
                                        target_filters.venue_id = UUID(selected.id)
                                    else:
                                        target_filters.organization_id = UUID(selected.id)
                                    comparisons.append(
                                        ComparisonItem(
                                            target=selected,
                                            value=await count_selection(
                                                connection, settings, target_filters, metric, area
                                            ),
                                        )
                                    )
                                result = ComparisonResult(metric=metric, items=comparisons)
                            elif plan.entity_type == "event":
                                # Structured events always have explicit occurrence ordering.
                                result = RecordsResult(
                                    items=await chronological_records(
                                        connection,
                                        settings,
                                        filters,
                                        resolution.area,
                                        plan.ordering or "asc",
                                        filters.page_size,
                                    )
                                )
                            else:
                                records = await research_page(
                                    connection, settings, filters, observed_at, resolution.area
                                )
                                result = RecordsResult(
                                    items=list(records.items), total=records.pagination.total
                                )
                    execution_ms = (perf_counter() - before) * 1000
            except (SQLAlchemyError, TimeoutError):
                raise APIError(
                    503,
                    "research_execution_unavailable",
                    "Research execution is temporarily unavailable.",
                ) from None
            except (ValueError, OverflowError):
                raise APIError(
                    502, "research_execution_invalid_plan", "The research plan is invalid."
                ) from None
        return ResearchExecutionResponse(
            query=plan.original_query,
            plan=plan_response,
            resolution=resolution.fields,
            result=result,
            execution=provenance,
            observed_at=observed_at,
            timezone=plan_response.timezone,
            diagnostics=ExecutionDiagnostics(
                planner_ms=planner_ms,
                resolution_ms=resolution_ms,
                execution_ms=execution_ms,
                total_ms=planner_ms + (perf_counter() - started) * 1000,
                returned_count=len(result.items)
                if isinstance(result, (RecordsResult, AggregateResult, ComparisonResult))
                else 0,
            ),
        )
