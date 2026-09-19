"""Short admin transactions and immutable candidate generations. Never source DML."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, func, literal_column, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import geocode_candidate as candidate
from app.admin_tables import geocode_request as request
from app.config import Settings
from app.errors import APIError
from app.repositories.geocode_sources import lookup_sources
from app.schemas.geocode import (
    GeocodeCandidate,
    GeocodeFilters,
    GeocodePage,
    GeocodeRequestDetail,
    GeocodeRequestSummary,
    GeocodeStatus,
)
from app.services.geo.geocoding import (
    QUERY_VERSION,
    SCORING_VERSION,
    display_address,
    query_fingerprint,
    source_fingerprint,
)


def fresh_values(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    return dict(
        source_fingerprint=source_fingerprint(row),
        query_fingerprint=query_fingerprint(row),
        query_version=QUERY_VERSION,
        scoring_version=SCORING_VERSION,
        status="pending",
        next_check_at=now,
        updated_at=now,
        checked_at=None,
        attempt_count=0,
        last_error=None,
        worker_id=None,
        lease_until=None,
    )


async def synchronize(
    admin: AsyncConnection, rows: list[dict[str, Any]], counters: dict[str, int] | None = None
) -> int:
    if not rows:
        return 0
    now = datetime.now(UTC)
    values = [
        dict(
            id=uuid4(),
            entity_type=row["entity_type"],
            entity_key=row["entity_key"],
            generation=1,
            created_at=now,
            **fresh_values(row, now),
        )
        for row in rows
        if row["point_missing"]
    ]
    if not values:
        return 0
    stmt = insert(request).values(values)
    async with admin.begin():
        result = await admin.execute(
            stmt.on_conflict_do_update(
                index_elements=[request.c.entity_type, request.c.entity_key],
                set_={
                    **{key: getattr(stmt.excluded, key) for key in fresh_values(rows[0], now)},
                    "generation": request.c.generation + 1,
                },
                # Algorithm deployments never cause automatic mass requeue.
                where=or_(
                    request.c.source_fingerprint != stmt.excluded.source_fingerprint,
                    request.c.status == "stale",
                ),
            ).returning(request.c.id, literal_column("xmax = 0").label("created"))
        )
        changed = result.all()
        if counters is not None:
            counters["requests_created"] += sum(bool(row.created) for row in changed)
        return len(changed)


async def mark_stale(admin: AsyncConnection, ids: list[UUID]) -> int:
    if not ids:
        return 0
    async with admin.begin():
        result = await admin.execute(
            update(request)
            .where(request.c.id.in_(ids), request.c.status != "stale")
            .values(
                status="stale",
                worker_id=None,
                lease_until=None,
                next_check_at=None,
                updated_at=func.clock_timestamp(),
            )
            .returning(request.c.id)
        )
        return len(result.all())


async def claim(admin: AsyncConnection, settings: Settings, owner: UUID) -> dict[str, Any] | None:
    async with admin.begin():
        row = (
            (
                await admin.execute(
                    select(request)
                    .where(
                        or_(
                            (request.c.status.in_(["pending", "failed", "not_found"]))
                            & (request.c.next_check_at <= func.clock_timestamp()),
                            (request.c.status == "checking")
                            & (request.c.lease_until <= func.clock_timestamp()),
                        )
                    )
                    .order_by(
                        case((request.c.status == "pending", 0), else_=1),
                        request.c.next_check_at,
                        request.c.id,
                    )
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        values = dict(
            status="checking",
            worker_id=owner,
            lease_until=func.clock_timestamp() + timedelta(seconds=settings.geocode_lease_seconds),
            updated_at=func.clock_timestamp(),
        )
        # One generation per evaluation, including manual/automatic refresh. Lost leases
        # have not committed candidates, so can safely reuse their generation.
        if row["checked_at"] is not None:
            values.update(generation=row["generation"] + 1, checked_at=None)
        result = await admin.execute(
            update(request).where(request.c.id == row["id"]).values(**values).returning(request)
        )
        return dict(result.mappings().one())


def fence(job: dict[str, Any], owner: UUID) -> Any:
    return (
        (request.c.id == job["id"])
        & (request.c.worker_id == owner)
        & (request.c.generation == job["generation"])
        & (request.c.status == "checking")
        & (request.c.lease_until > func.clock_timestamp())
    )


async def begin_attempt(
    admin: AsyncConnection,
    job: dict[str, Any],
    owner: UUID,
    row: dict[str, Any],
    settings: Settings,
) -> bool:
    values = dict(
        query_fingerprint=query_fingerprint(row, settings.geocode_max_candidates),
        query_version=QUERY_VERSION,
        scoring_version=SCORING_VERSION,
    )
    async with admin.begin():
        result = await admin.execute(
            update(request)
            .where(fence(job, owner))
            .values(**values, attempt_count=request.c.attempt_count + 1)
            .returning(request.c.id)
        )
        if result.first() is None:
            return False
    job.update(values)
    return True


async def finish(
    admin: AsyncConnection,
    settings: Settings,
    job: dict[str, Any],
    owner: UUID,
    status: GeocodeStatus,
    items: list[GeocodeCandidate],
) -> bool:
    now = datetime.now(UTC)
    next_check = (
        now + timedelta(minutes=settings.geocode_failed_retry_minutes)
        if status == "failed"
        else now + timedelta(days=settings.geocode_not_found_retry_days)
        if status == "not_found"
        else None
    )
    async with admin.begin():
        current = (
            await admin.execute(select(request.c.id).where(fence(job, owner)).with_for_update())
        ).first()
        if current is None:
            return False
        if items:
            await admin.execute(
                insert(candidate),
                [
                    dict(
                        **item.model_dump(exclude={"osm_url"}),
                        request_id=job["id"],
                        generation=job["generation"],
                        source_fingerprint=job["source_fingerprint"],
                        query_fingerprint=job["query_fingerprint"],
                        query_version=job["query_version"],
                        scoring_version=job["scoring_version"],
                        created_at=now,
                    )
                    for item in items
                ],
            )
        await admin.execute(
            update(request)
            .where(request.c.id == job["id"])
            .values(
                status=status,
                checked_at=now,
                next_check_at=next_check,
                updated_at=now,
                last_error="provider_unavailable" if status == "failed" else None,
                worker_id=None,
                lease_until=None,
            )
        )
        return True


async def retry(admin: AsyncConnection, source: AsyncConnection, key: UUID) -> None:
    async with admin.begin():
        row = (
            (await admin.execute(select(request).where(request.c.id == key).with_for_update()))
            .mappings()
            .first()
        )
        if row is None:
            raise APIError(404, "geocode_request_not_found", "Location request not found.")
        job = dict(row)
        current = (await lookup_sources(source, [job])).get((job["entity_type"], job["entity_key"]))
        if current is None or not current["point_missing"]:
            raise APIError(
                409, "geocode_no_longer_needed", "Location suggestion is no longer needed."
            )
        if job["status"] in ("pending", "checking"):
            raise APIError(409, "geocode_retry_not_allowed", "Location check is already queued.")
        await admin.execute(
            update(request)
            .where(request.c.id == key)
            .values(
                **fresh_values(current, datetime.now(UTC)),
                generation=request.c.generation + 1,
            )
        )


async def enrich(
    admin: AsyncConnection, source: AsyncConnection, jobs: list[dict[str, Any]]
) -> list[GeocodeRequestDetail]:
    sources = await lookup_sources(source, jobs)
    groups: dict[UUID, list[GeocodeCandidate]] = {}
    if jobs:
        rows = (
            await admin.execute(
                select(candidate)
                .where(
                    tuple_(candidate.c.request_id, candidate.c.generation).in_(
                        [(job["id"], job["generation"]) for job in jobs]
                    )
                )
                .order_by(candidate.c.request_id, candidate.c.rank)
            )
        ).mappings()
        for row in rows:
            groups.setdefault(row["request_id"], []).append(
                GeocodeCandidate.model_validate(dict(row))
            )
    results = []
    for job in jobs:
        current = sources.get((job["entity_type"], job["entity_key"]))
        stale = (
            current is None
            or not current["point_missing"]
            or source_fingerprint(current) != job["source_fingerprint"]
        )
        items = (
            groups.get(job["id"], [])
            if not stale and job["status"] in ("candidate", "ambiguous")
            else []
        )
        results.append(
            GeocodeRequestDetail.model_validate(
                dict(
                    **{**job, "status": "stale" if stale else job["status"]},
                    entity_name=current["name"] if current else str(job["entity_key"]),
                    source_address=display_address(current) if current else "",
                    candidate_count=len(items),
                    best_candidate=items[0] if items else None,
                    candidates=items,
                )
            )
        )
    return results


async def page(
    admin: AsyncConnection, source: AsyncConnection, filters: GeocodeFilters
) -> GeocodePage:
    async with admin.begin():
        predicates = []
        if filters.status:
            predicates.append(request.c.status == filters.status)
        if filters.entity_type:
            predicates.append(request.c.entity_type == filters.entity_type)
        total = (
            await admin.execute(select(func.count()).select_from(request).where(*predicates))
        ).scalar_one()
        jobs = [
            dict(row)
            for row in (
                await admin.execute(
                    select(request)
                    .where(*predicates)
                    .order_by(request.c.updated_at.desc(), request.c.id)
                    .offset((filters.page - 1) * filters.page_size)
                    .limit(filters.page_size)
                )
            ).mappings()
        ]
        details = await enrich(admin, source, jobs)
        counts = {
            row[0]: row[1]
            for row in (
                await admin.execute(
                    select(request.c.status, func.count()).group_by(request.c.status)
                )
            )
        }

    return GeocodePage.model_validate(
        dict(
            items=[
                GeocodeRequestSummary.model_validate(item.model_dump()).model_dump()
                for item in details
            ],
            pagination=dict(
                page=filters.page,
                page_size=filters.page_size,
                total=total,
                pages=(total + filters.page_size - 1) // filters.page_size,
            ),
            counts=counts,
        )
    )


async def detail(
    admin: AsyncConnection, source: AsyncConnection, key: UUID
) -> GeocodeRequestDetail:
    async with admin.begin():
        row = (await admin.execute(select(request).where(request.c.id == key))).mappings().first()
        if row is None:
            raise APIError(404, "geocode_request_not_found", "Location request not found.")
        return (await enrich(admin, source, [dict(row)]))[0]
