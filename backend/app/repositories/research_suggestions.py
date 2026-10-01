"""Admin-only learning transactions and one indexed suggestion retrieval."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import research_query_history as history
from app.admin_tables import research_query_suggestion as suggestions
from app.admin_tables import research_query_suggestion_event as events
from app.errors import APIError
from app.schemas.research_planner import ResearchQueryPlan
from app.schemas.research_suggestions import (
    Impression,
    Selection,
    SuggestionFilters,
    SuggestionItem,
    Suggestions,
)
from app.services import research_suggestions as rules

RECEIPT_TTL = timedelta(minutes=10)


def public() -> sa.ColumnElement[bool]:
    return sa.and_(
        suggestions.c.is_eligible,
        ~suggestions.c.is_blocked,
        suggestions.c.success_count >= rules.MIN_SUCCESSES,
    )


async def lookup(connection: AsyncConnection, filters: SuggestionFilters) -> Suggestions:
    prefix = rules.normalize(filters.q)
    if len(prefix) < 2:
        raise APIError(422, "invalid_input", "A prefix needs at least two characters.")
    request_id = uuid4()
    if not rules.eligible(filters.q):
        return Suggestions(request_id=request_id, suggestions=[])
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    c = suggestions.c
    starts = c.normalized_query.like(escaped + "%", escape="\\")
    age = sa.func.greatest(0, sa.extract("epoch", sa.func.now() - c.last_used_at) / 86400)
    rank = (
        sa.case((starts, rules.PREFIX_WEIGHT), else_=0)
        + rules.FREQUENCY_WEIGHT * sa.func.ln(c.success_count + 1)
        + rules.SELECTION_WEIGHT * sa.func.ln(c.suggestion_selections + 1)
        + rules.CONVERSION_WEIGHT * sa.func.ln(c.successful_selections + 1)
        + rules.RECENCY_WEIGHT / (1 + age / rules.RECENCY_DAYS)
        + rules.CTR_WEIGHT
        * sa.func.least(1, (c.suggestion_selections + 2.0) / (c.suggestion_impressions + 10.0))
    )
    statement = sa.select(c.id, c.display_query).where(
        public(),
        c.search_prefixes.contains([prefix.split()[0]]),
        sa.or_(starts, c.normalized_query.like("% " + escaped + "%", escape="\\")),
    )
    if filters.language:
        statement = statement.where(c.language.in_([filters.language, "und"]))
    rows = (
        await connection.execute(
            statement.order_by(rank.desc(), c.normalized_query.collate("C"), c.id).limit(
                filters.limit
            )
        )
    ).mappings()
    return Suggestions(
        request_id=request_id,
        suggestions=[
            SuggestionItem(id=row["id"], query=row["display_query"], position=position)
            for position, row in enumerate(rows, 1)
        ],
    )


async def impression(connection: AsyncConnection, body: Impression) -> None:
    if not rules.eligible(body.prefix):
        return
    now = datetime.now(UTC)
    # Lock a rendered set in deterministic order; three bounded statements, no N+1.
    rows = (
        await connection.execute(
            sa.select(suggestions.c.id, suggestions.c.normalized_query)
            .where(suggestions.c.id.in_([item.id for item in body.suggestions]), public())
            .order_by(suggestions.c.id)
            .with_for_update()
        )
    ).mappings()
    prefix = rules.normalize(body.prefix)
    matching = {
        row["id"]
        for row in rows
        if row["normalized_query"].startswith(prefix) or " " + prefix in row["normalized_query"]
    }
    values = [
        dict(
            id=uuid4(),
            suggestion_id=item.id,
            request_id=body.request_id,
            event_type="impression",
            prefix=prefix,
            position=item.position,
            created_at=now,
        )
        for item in body.suggestions
        if item.id in matching
    ]
    if not values:
        return
    inserted = (
        (
            await connection.execute(
                insert(events)
                .values(values)
                .on_conflict_do_nothing()
                .returning(events.c.suggestion_id)
            )
        )
        .scalars()
        .all()
    )
    if inserted:
        await connection.execute(
            suggestions.update()
            .where(suggestions.c.id.in_(inserted))
            .values(suggestion_impressions=suggestions.c.suggestion_impressions + 1, updated_at=now)
        )


async def select(connection: AsyncConnection, body: Selection) -> UUID:
    now = datetime.now(UTC)
    exists = (
        await connection.execute(
            sa.select(suggestions.c.id)
            .where(suggestions.c.id == body.suggestion_id, public())
            .with_for_update()
        )
    ).scalar_one_or_none()
    shown = (
        await connection.execute(
            sa.select(events.c.id).where(
                events.c.request_id == body.request_id,
                events.c.suggestion_id == body.suggestion_id,
                events.c.event_type == "impression",
                events.c.position == body.position,
                events.c.created_at >= now - RECEIPT_TTL,
            )
        )
    ).scalar_one_or_none()
    if not exists or not shown:
        raise APIError(422, "invalid_input", "Suggestion is unavailable or was not shown.")
    receipt = (
        await connection.execute(
            insert(events)
            .values(
                id=uuid4(),
                suggestion_id=body.suggestion_id,
                request_id=body.request_id,
                event_type="selection",
                position=body.position,
                created_at=now,
            )
            .on_conflict_do_nothing()
            .returning(events.c.id)
        )
    ).scalar_one_or_none()
    if receipt:
        await connection.execute(
            suggestions.update()
            .where(suggestions.c.id == body.suggestion_id)
            .values(
                suggestion_selections=suggestions.c.suggestion_selections + 1,
                last_selected_at=now,
                updated_at=now,
            )
        )
        return UUID(str(receipt))
    return UUID(
        str(
            (
                await connection.execute(
                    sa.select(events.c.id).where(
                        events.c.request_id == body.request_id,
                        events.c.suggestion_id == body.suggestion_id,
                        events.c.event_type == "selection",
                    )
                )
            ).scalar_one()
        )
    )


async def learn(
    connection: AsyncConnection, query: str, plan: ResearchQueryPlan, receipt: UUID | None
) -> None:
    now = datetime.now(UTC)
    safe = rules.eligible(query)
    normalized = rules.normalize(query) if safe else None
    display = rules.display_query(query) if safe else None
    suggestion_id = None
    request_id = None
    if safe:
        # The unique upsert serializes counter and conversion changes for this query.
        suggestion_id = (
            await connection.execute(
                insert(suggestions)
                .values(
                    id=uuid4(),
                    normalized_query=normalized,
                    display_query=display,
                    language="und",
                    search_prefixes=rules.search_prefixes(normalized or ""),
                    success_count=1,
                    first_used_at=now,
                    last_used_at=now,
                    created_at=now,
                    updated_at=now,
                    is_eligible=True,
                    is_blocked=False,
                )
                .on_conflict_do_update(
                    index_elements=[suggestions.c.normalized_query],
                    set_={
                        "success_count": suggestions.c.success_count + 1,
                        "display_query": display,
                        "last_used_at": now,
                        "updated_at": now,
                    },
                )
                .returning(suggestions.c.id)
            )
        ).scalar_one()
        if receipt:
            request_id = (
                await connection.execute(
                    sa.select(events.c.request_id).where(
                        events.c.id == receipt,
                        events.c.suggestion_id == suggestion_id,
                        events.c.event_type == "selection",
                        events.c.created_at >= now - RECEIPT_TTL,
                        ~sa.exists(
                            sa.select(history.c.id).where(
                                history.c.suggestion_id == suggestion_id,
                                history.c.suggestion_request_id == events.c.request_id,
                            )
                        ),
                    )
                )
            ).scalar_one_or_none()
        if request_id:
            await connection.execute(
                suggestions.update()
                .where(suggestions.c.id == suggestion_id)
                .values(successful_selections=suggestions.c.successful_selections + 1)
            )
    await connection.execute(
        history.insert().values(
            id=uuid4(),
            query_text=display,
            normalized_query=normalized,
            language="und",
            intent=plan.intent,
            entity_type=plan.entity_type,
            metric=plan.metric,
            # Free-text planner slots are intentionally not retained.
            suggestion_id=suggestion_id if request_id else None,
            suggestion_request_id=request_id,
            source="suggestion" if request_id else "direct",
            successful=True,
            is_eligible=safe,
            created_at=now,
        )
    )
