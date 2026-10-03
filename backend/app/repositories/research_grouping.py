"""Ordered cell aggregation on the shared authoritative occurrence selection."""

from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.administrative_execution import COLUMNS, execution_sql, validate_selection
from app.repositories.research import parameters, research_sql
from app.repositories.research_areas import ResolvedResearchArea
from app.repositories.research_execution import grouping_sql
from app.research.capabilities import boundary_execution, grouped_execution
from app.research.plan import InternalResearchPlan, ResolvedResearchPlan
from app.research.sql_provenance import execute_research_sql
from app.schemas.research_execution import (
    ExecutionMetric,
    GroupCoordinate,
    GroupedItem,
    GroupedResult,
)


def grouped_sql(
    plan: InternalResearchPlan,
    resolved: ResolvedResearchPlan,
    settings: Settings,
    area: ResolvedResearchArea | None,
) -> tuple[str, dict[str, Any]]:
    if not grouped_execution(plan):
        raise ValueError("unsupported_grouped_selection")
    if boundary_execution(plan):
        prefix, params = execution_sql(resolved, settings)
        prefix += f", selected AS (SELECT {COLUMNS},point FROM matched)"
    else:
        prefix = f"WITH selected AS ({research_sql(occurrences=True)})"
        params = parameters(resolved.filters, settings, area)
    projections, joins, groups, predicates, ties = [], [], [], [], []
    for index, dimension in enumerate(plan.groupings):
        if dimension == "month":
            # Local event dates, not UTC timestamps; cyclical month across years.
            key = "lpad(extract(month FROM selected.start_date)::integer::text,2,'0')"
            name, join = key, ""
        elif dimension == "weekday":
            # ISO Monday=1 ... Sunday=7; event-local date, independent of locale.
            key = "extract(isodow FROM selected.start_date)::integer::text"
            name, join = key, ""
        elif dimension == "municipality":
            key, name = "municipality.area_id", "municipality.name"
            join = (
                "JOIN inventory municipality ON selected.point IS NOT NULL "
                "AND ST_CoveredBy(selected.point,municipality.boundary)"
            )
        else:
            key, name, join = grouping_sql(dimension, axis=index)
        projections += [f"{key} key_{index}", f"{name} name_{index}"]
        groups += [key, name]
        predicates.append(f"{key} IS NOT NULL")
        joins.append(join)
        ties += [f'lower({name}) COLLATE "C"', f'({key}) COLLATE "C"']
    if "event_type" in plan.groupings and "genre" in plan.groupings:
        type_index = plan.groupings.index("event_type")
        genre_index = plan.groupings.index("genre")
        predicates.append(f"l_{type_index}.type_id=l_{genre_index}.type_id")
    count = {"occurrence_count": "selected.date_key", "event_count": "selected.entity_key"}[
        plan.metric
    ]
    direction = {"asc": "ASC", "desc": "DESC", None: None}[plan.ordering]
    order = ([f"value {direction}"] if direction else []) + ties
    params["cell_limit"] = plan.limit or 20
    return (
        prefix
        + f""" SELECT {",".join(projections)},count(DISTINCT {count}) value
        FROM selected {" ".join(joins)} WHERE {" AND ".join(predicates)}
        GROUP BY {",".join(dict.fromkeys(groups))}
        ORDER BY {",".join(order)} LIMIT :cell_limit""",
        params,
    )


async def grouped_selection(
    connection: AsyncConnection,
    settings: Settings,
    plan: InternalResearchPlan,
    resolved: ResolvedResearchPlan,
    area: ResolvedResearchArea | None,
) -> GroupedResult:
    if boundary_execution(plan):
        prefix, params = execution_sql(resolved, settings)
        await validate_selection(connection, resolved, prefix, params)
    sql, params = grouped_sql(plan, resolved, settings, area)
    rows = (
        await execute_research_sql(
            connection, text(sql), params, label="Mehrdimensionale Auswertung"
        )
    ).mappings()
    return GroupedResult(
        metric=cast(ExecutionMetric, plan.metric),
        dimensions=list(plan.groupings),
        ordering=plan.ordering,
        limit=plan.limit or 20,
        items=[
            GroupedItem(
                coordinates=[
                    GroupCoordinate(dimension=dimension, key=row[f"key_{i}"], name=row[f"name_{i}"])
                    for i, dimension in enumerate(plan.groupings)
                ],
                value=row["value"],
            )
            for row in rows
        ],
    )
