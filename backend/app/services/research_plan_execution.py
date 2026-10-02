"""Deterministic execution of validated server-side plans. No inference or persistence."""

import asyncio
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
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
    spatial_records,
    taxonomy_selection,
)
from app.repositories.research_resolution import Resolution, resolve_plan
from app.research.capabilities import require_supported
from app.research.context import ResearchExecutionContext
from app.research.geography import (
    AdministrativeAreaRef,
    administrative_constraints,
    uses_user_location,
)
from app.research.outcome import ResearchExecutionOutcome
from app.research.plan import InternalResearchPlan
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
    SpatialResult,
    TaxonomyResult,
)
from app.services.semantic_search import semantic_research


def temporal_bounds(
    plan: InternalResearchPlan,
    context: ResearchExecutionContext,
) -> tuple[date | None, date | None]:
    # reference_date is already a local date in this validated zone. Calendar
    # arithmetic deliberately avoids UTC offsets, including across DST changes.
    ZoneInfo(context.timezone)
    ref = context.reference_date
    monday = ref - timedelta(days=ref.weekday())
    match plan.temporal.period:
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
            return plan.temporal.from_date, plan.temporal.to_date


def execution_filters(
    plan: InternalResearchPlan, context: ResearchExecutionContext, resolution: Resolution
) -> ExecutionFilters:
    # SQL receives only verified IDs/boundaries. A resolver omission must not drop
    # an administrative constraint and turn a scoped query into a global query.
    constraints = administrative_constraints(plan.spatial_constraints)
    if constraints:
        resolved = administrative_constraints(resolution.spatial_constraints)
        reference = resolved[0].reference if len(resolved) == 1 else None
        if (
            len(constraints) != 1
            or resolution.area is None
            or not isinstance(reference, AdministrativeAreaRef)
            or reference.resolved_id != resolution.area.area.id
            or reference.boundary is None
            or reference.boundary.area_id != reference.resolved_id
            or resolved[0].relation != constraints[0].relation
        ):
            raise APIError(502, "research_execution_invalid_plan", "Area resolution is incomplete.")
    start, end = temporal_bounds(plan, context)
    filters = ExecutionFilters(
        place=resolution.place,
        entity_type=plan.entity_type,
        from_date=start,
        to_date=end,
        time_from=plan.temporal.time_from,
        time_of_day=plan.temporal.time_of_day,
        area_relation=resolution.area_relation,
        page_size=plan.limit or 20,
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
        plan: InternalResearchPlan,
        context: ResearchExecutionContext,
        *,
        planner_ms: float,
    ) -> ResearchExecutionOutcome:
        started = perf_counter()
        resolution = Resolution()
        provenance = ExecutionProvenance()
        resolution_ms = execution_ms = 0.0
        observed_at = datetime.now(UTC)
        if plan.unsupported_reason is not None:
            raise APIError(422, "research_plan_unsupported", "This research plan is unsupported.")
        location_satisfied = (
            uses_user_location(plan.spatial_constraints)
            and context.location_context is not None
            and plan.clarification == "needs_location"
        )
        if plan.clarification != "none" and not location_satisfied:
            result: ExecutionResult = ExecutionClarification(
                reason="planner", planner_state=plan.clarification
            )
        else:
            if (
                plan.clarification != "none" and not location_satisfied
            ) or context.timezone != settings.event_timezone:
                raise APIError(
                    502, "research_execution_invalid_plan", "The research plan is invalid."
                )
            require_supported(plan)
            try:
                # Bound the complete resolution stage, in addition to DB statement limits.
                async with asyncio.timeout(settings.db_timeout_seconds):
                    resolution = await resolve_plan(request, settings, plan, context)
                resolution_ms = (perf_counter() - started) * 1000
                if resolution.clarification is not None:
                    result = resolution.clarification
                else:
                    filters = execution_filters(plan, context, resolution)
                    provenance = ExecutionProvenance(
                        from_date=filters.from_date,
                        to_date=filters.to_date,
                        time_from=filters.time_from,
                        time_of_day=filters.time_of_day,
                        area_relation=filters.area_relation,
                        event_type_ids=filters.event_type_ids,
                        category_ids=filters.category_ids,
                        genre_keys=filters.genre_keys,
                        structured=True,
                        semantic=plan.semantic is not None,
                    )
                    before = perf_counter()
                    if plan.semantic is not None:
                        semantic_filters = ExecutionSemanticFilters(
                            place=filters.place,
                            **{
                                k: v
                                for k, v in filters.model_dump().items()
                                if k not in {"q", "sort"}
                            },
                            q="\n".join(
                                dict.fromkeys(
                                    term
                                    for term in (plan.semantic.query, plan.semantic.focus)
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
                            if plan.intent == "taxonomy":
                                assert plan.taxonomy is not None
                                result = await taxonomy_selection(
                                    connection,
                                    settings,
                                    filters,
                                    plan.taxonomy,
                                    resolution.area,
                                    filters.page_size,
                                    plan.ordering or "asc",
                                )
                            elif plan.intent == "spatial_rank":
                                assert plan.spatial_metric is not None and plan.ordering is not None
                                result = SpatialResult(
                                    spatial_metric=plan.spatial_metric,
                                    ordering=plan.ordering,
                                    items=await spatial_records(
                                        connection,
                                        settings,
                                        filters,
                                        resolution.area,
                                        plan.spatial_metric,
                                        plan.ordering,
                                        filters.page_size,
                                    ),
                                )
                            elif plan.intent == "count":
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
                                        ordering=plan.ordering or "desc",
                                        limit=filters.page_size,
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
        return ResearchExecutionOutcome(
            resolution=resolution.fields,
            result=result,
            execution=provenance,
            observed_at=observed_at,
            diagnostics=ExecutionDiagnostics(
                planner_ms=planner_ms,
                resolution_ms=resolution_ms,
                execution_ms=execution_ms,
                total_ms=planner_ms + (perf_counter() - started) * 1000,
                returned_count=len(result.items)
                if isinstance(
                    result,
                    (
                        RecordsResult,
                        AggregateResult,
                        ComparisonResult,
                        TaxonomyResult,
                        SpatialResult,
                    ),
                )
                else 0,
            ),
        )
