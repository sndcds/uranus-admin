import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import check_run, finding
from app.config import Settings
from app.errors import APIError
from app.repositories.spatial import SPATIAL_TYPES
from app.repositories.venues import RULE
from app.schemas.checks import CheckRun, ReviewUpdate
from app.schemas.cursor import CursorPagination, FindingCursor, decode, encode, scope
from app.schemas.dashboard import QualityCounts
from app.schemas.finding import Finding, FindingFilters, FindingPage, Pagination, Severity
from app.services.geo.membership import MEMBERSHIP_BATCH_SIZE, spatial_membership
from app.services.quality.core import CORE_RULES, RuleResult
from app.services.quality.engine import scan
from app.services.quality.priority import priority_details
from app.services.queues import QUEUE_RULES

# Short persistence/review critical section only; scanning never holds this lock.
LOCK_KEY = 723114905
QUEUE_LOCK_KEY = 723114906

# Explicit labels keep result mappings independent of physical legacy column names.
FINDING_COLUMNS = tuple(column.label(column.key) for column in finding.c)


async def lock(connection: AsyncConnection) -> None:
    try:
        acquired = (
            await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
        ).scalar_one()
        await connection.commit()
    except BaseException:
        # Never return a possibly locked session to the pool after cancellation/I/O failure.
        await connection.invalidate()
        raise
    if not acquired:
        raise APIError(409, "check_run_conflict", "A check or review is already in progress.")


async def unlock(connection: AsyncConnection) -> None:
    try:
        if connection.in_transaction():
            await connection.rollback()
        await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
        await connection.commit()
    except BaseException:
        await connection.invalidate()
        raise


async def persist_results(
    connection: AsyncConnection, results: list[RuleResult], now: datetime
) -> None:
    # An incomplete run cannot resolve ANY finding, including successful earlier rules.
    complete = bool(results) and all(result.success for result in results)
    for result in results:
        if not result.success:
            continue
        detected = {item.id for item in result.findings}
        existing = {
            row["id"]: dict(row)
            for row in (
                await connection.execute(
                    select(*FINDING_COLUMNS).where(finding.c.rule == result.rule).with_for_update()
                )
            ).mappings()
        }
        for item in result.findings:
            old = existing.get(item.id)
            status = old["status"] if old else "open"
            # Evidence changes invalidate exceptions. Observation time / priority aging does not.
            evidence = {
                "message": item.message,
                "severity": item.severity.value,
                "metadata": {
                    key: value for key, value in item.metadata.items() if key != "age_days"
                },
            }
            changed = bool(old and old["metadata"].get("evidence") != evidence)
            expired = bool(
                old and status == "snoozed" and old["snoozed_until"] and old["snoozed_until"] <= now
            )
            if status == "resolved" or expired or (changed and status in {"exception", "ignored"}):
                status = "open"
            values = {
                "id": item.id,
                "rule": item.rule,
                "severity": item.severity.value,
                "entity_type": item.entity_type,
                "entity_key": item.entity_key,
                "field": item.field,
                "message": item.message,
                "first_seen_at": old["first_seen_at"] if old else now,
                "last_seen_at": now,
                "resolved_at": None,
                "status": status,
                "metadata": {
                    "finding": item.model_dump(mode="json", exclude={"entity_id"}),
                    "evidence": evidence,
                },
            }
            statement = insert(finding).values(**values)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[finding.c.id],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in {"id", "first_seen_at"}
                    },
                )
            )
        if complete:
            for old in existing.values():
                if (
                    old["id"] not in detected
                    and (old["entity_type"], old["entity_key"]) in result.covered
                    and old["status"] != "resolved"
                ):
                    await connection.execute(
                        update(finding)
                        .where(finding.c.id == old["id"])
                        .values(status="resolved", resolved_at=now)
                    )


async def enqueue_check(admin: AsyncConnection) -> CheckRun:
    async with admin.begin():
        await admin.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUEUE_LOCK_KEY})
        if (
            await admin.execute(
                select(check_run.c.id).where(check_run.c.status.in_(["queued", "running"]))
            )
        ).first():
            raise APIError(409, "check_run_conflict", "A check is already queued or running.")
        row = (
            (
                await admin.execute(
                    insert(check_run)
                    .values(id=uuid4(), started_at=datetime.now(UTC), status="queued")
                    .returning(check_run)
                )
            )
            .mappings()
            .one()
        )
        return CheckRun.model_validate(dict(row))


async def claim_check(admin: AsyncConnection, settings: Settings) -> tuple[UUID, UUID] | None:
    async with admin.begin():
        await admin.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUEUE_LOCK_KEY})
        await admin.execute(
            update(check_run)
            .where(
                check_run.c.status == "running",
                check_run.c.lease_until <= func.clock_timestamp(),
            )
            .values(
                status="failed",
                finished_at=func.clock_timestamp(),
                error_message="Worker interrupted; no findings resolved.",
                lease_until=None,
                worker_id=None,
            )
        )
        run_id = (
            await admin.execute(
                select(check_run.c.id)
                .where(check_run.c.status == "queued")
                .order_by(check_run.c.started_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if run_id is None:
            return None
        worker_id = uuid4()
        await admin.execute(
            update(check_run)
            .where(check_run.c.id == run_id)
            .values(
                status="running",
                worker_id=worker_id,
                lease_until=func.clock_timestamp()
                + timedelta(seconds=settings.check_job_lease_seconds),
            )
        )
        return run_id, worker_id


async def renew_lease(
    admin: AsyncConnection, settings: Settings, run_id: UUID, worker_id: UUID
) -> bool:
    async with admin.begin():
        owned = select(check_run.c.id).where(
            check_run.c.id == run_id,
            check_run.c.worker_id == worker_id,
            check_run.c.status == "running",
        )
        available = (
            await admin.execute(owned.with_for_update(skip_locked=True))
        ).scalar_one_or_none()
        if available is None:
            # Final persistence holds the owned row lock until its atomic commit.
            # Do not wait behind it and cancel a healthy worker on command timeout.
            # This read never extends an expired lease or permits stale persistence.
            return (await admin.execute(owned)).scalar_one_or_none() is not None
        result = await admin.execute(
            update(check_run)
            .where(
                check_run.c.id == run_id,
                check_run.c.worker_id == worker_id,
                check_run.c.status == "running",
                check_run.c.lease_until > func.clock_timestamp(),
            )
            .values(
                lease_until=func.clock_timestamp()
                + timedelta(seconds=settings.check_job_lease_seconds)
            )
        )
        return result.rowcount == 1


async def fail_job(admin: AsyncConnection, run_id: UUID, worker_id: UUID) -> None:
    if admin.in_transaction():
        await admin.rollback()
    async with admin.begin():
        await admin.execute(
            update(check_run)
            .where(
                check_run.c.id == run_id,
                check_run.c.worker_id == worker_id,
                check_run.c.status == "running",
            )
            .values(
                status="failed",
                finished_at=func.clock_timestamp(),
                error_message="Check interrupted or failed; no findings resolved.",
                worker_id=None,
                lease_until=None,
            )
        )


async def execute_check(
    source: AsyncConnection,
    admin: AsyncConnection,
    settings: Settings,
    run_id: UUID,
    worker_id: UUID,
) -> CheckRun:
    try:
        results = await scan(source, settings, datetime.now(UTC))
        expected_rules = {RULE, *CORE_RULES, *QUEUE_RULES}
        if (
            len(results) != len(expected_rules)
            or {result.rule for result in results} != expected_rules
            or not all(result.success for result in results)
        ):
            raise RuntimeError("Incomplete scan")
        async with admin.begin():
            # Only this short transaction serializes with human review. The fresh rows
            # read by persist_results retain reviews made while the source scan ran.
            await admin.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
            owned = (
                await admin.execute(
                    select(check_run.c.id)
                    .where(
                        check_run.c.id == run_id,
                        check_run.c.worker_id == worker_id,
                        check_run.c.status == "running",
                        check_run.c.lease_until > func.clock_timestamp(),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if owned is None:
                raise RuntimeError("Worker lease lost")
            finished = datetime.now(UTC)
            await persist_results(admin, results, finished)
            await admin.execute(
                update(check_run)
                .where(check_run.c.id == run_id)
                .values(
                    status="success",
                    finished_at=finished,
                    rule_count=len(results),
                    finding_count=sum(len(result.findings) for result in results),
                    worker_id=None,
                    lease_until=None,
                    rule_results={
                        result.rule: {
                            "success": True,
                            "covered": [list(key) for key in sorted(result.covered)],
                            "finding_count": len(result.findings),
                        }
                        for result in results
                    },
                )
            )
    except BaseException as exc:
        logging.getLogger("admin.checks").error(
            "check_failed", extra={"error_type": type(exc).__name__}
        )
        await fail_job(admin, run_id, worker_id)
        if not isinstance(exc, Exception):
            raise
    async with admin.begin():
        row = (
            (await admin.execute(select(check_run).where(check_run.c.id == run_id)))
            .mappings()
            .one()
        )
        return CheckRun.model_validate(dict(row))


async def run_check(
    source: AsyncConnection, admin: AsyncConnection, settings: Settings
) -> CheckRun:
    """In-process worker entry used by integration tests; never called by an HTTP route."""
    await enqueue_check(admin)
    job = await claim_check(admin, settings)
    if job is None:
        raise APIError(409, "check_run_conflict", "Another worker claimed this check.")
    return await execute_check(source, admin, settings, *job)


def stored_finding(row: dict[str, Any]) -> Finding:
    payload = row["metadata"].get("finding", {})
    # Legacy foundation rows may not yet have display/relevance metadata.
    payload = {
        **priority_details(Severity(row["severity"]), published=False, soon=False, upcoming=False),
        "entity_name": row["entity_key"],
        "organization_id": None,
        "organization_name": None,
        **payload,
    }
    payload.update(
        {
            key: row[key]
            for key in (
                "id",
                "rule",
                "severity",
                "entity_type",
                "field",
                "message",
                "first_seen_at",
                "last_seen_at",
                "resolved_at",
                "status",
                "assigned_to",
                "reviewed_by",
                "reviewed_subject",
                "reviewed_at",
                "snoozed_until",
                "comment",
                "exception_reason",
            )
        }
    )
    payload["entity_key"] = row["entity_key"]
    return Finding.model_validate(payload)


def stored_priority_score() -> Any:
    fallback = case(
        *[
            (
                finding.c.severity == severity.value,
                priority_details(severity, published=False, soon=False, upcoming=False)[
                    "priority_score"
                ],
            )
            for severity in Severity
        ]
    )
    return func.coalesce(finding.c.metadata["finding"]["priority_score"].as_integer(), fallback)


async def persisted_page(
    admin: AsyncConnection,
    filters: FindingFilters,
    now: datetime,
    source: AsyncConnection | None = None,
    geo_scope_wkb: bytes | None = None,
) -> FindingPage:
    if geo_scope_wkb is not None:
        if source is None:
            raise ValueError("Spatial findings require a source connection")
        return await spatial_persisted_page(admin, source, filters, now, geo_scope_wkb)
    cursor_mode = filters.cursor is not None
    expected_scope = scope(filters)
    position = (
        decode(filters.cursor, FindingCursor, expected_scope)
        if filters.cursor is not None and filters.cursor != "start"
        else None
    )
    conditions = []
    for key in ("severity", "entity_type", "entity_key", "rule", "status"):
        if (value := getattr(filters, key)) is not None:
            conditions.append(finding.c[key] == value)
    if filters.organization_id is not None:
        conditions.append(
            finding.c.metadata["finding"]["organization_id"].as_string()
            == str(filters.organization_id)
        )
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        total = int(
            (
                await admin.execute(select(func.count()).select_from(finding).where(*conditions))
            ).scalar_one()
        )
        if position:
            score = stored_priority_score()
            conditions.append(
                (score < position.priority_score)
                | ((score == position.priority_score) & (finding.c.id.collate("C") > position.id))
            )
        rows = (
            await admin.execute(
                select(*FINDING_COLUMNS)
                .where(*conditions)
                .order_by(stored_priority_score().desc(), finding.c.id.collate("C"))
                .limit(filters.page_size + int(cursor_mode))
                .offset(0 if cursor_mode else (filters.page - 1) * filters.page_size)
            )
        ).mappings()
        items = [stored_finding(dict(row)) for row in rows]
        has_more = cursor_mode and len(items) > filters.page_size
        items = items[: filters.page_size]
        next_cursor = (
            encode(
                FindingCursor(
                    scope=expected_scope, priority_score=items[-1].priority_score, id=items[-1].id
                )
            )
            if has_more
            else None
        )
        return FindingPage(
            items=items,
            cursor_pagination=CursorPagination(
                page_size=filters.page_size, next_cursor=next_cursor, has_more=has_more
            )
            if cursor_mode
            else None,
            mode="persisted",
            observed_at=now,
            pagination=Pagination(
                page=filters.page,
                page_size=filters.page_size,
                total=total,
                pages=(total + filters.page_size - 1) // filters.page_size,
            ),
        )


async def persisted_counts(
    admin: AsyncConnection,
    source: AsyncConnection | None = None,
    geo_scope_wkb: bytes | None = None,
) -> tuple[QualityCounts, int]:
    if geo_scope_wkb is not None:
        if source is None:
            raise ValueError("Spatial counts require a source connection")
        return await spatial_persisted_counts(admin, source, geo_scope_wkb)
    # Resolved records remain in history, but no longer count as current quality concerns.
    async with admin.begin():
        rows = (
            (
                await admin.execute(
                    select(
                        func.count().label("total"),
                        func.count().filter(finding.c.severity == "error").label("errors"),
                        func.count().filter(finding.c.severity == "warning").label("warnings"),
                        func.count().filter(finding.c.severity == "info").label("info"),
                        func.count()
                        .filter(
                            (finding.c.metadata["finding"]["priority"].as_integer() <= 2)
                            | finding.c.metadata["finding"]["priority_reasons"].contains(
                                ["published_soon"]
                            )
                        )
                        .label("urgent"),
                        finding.c.rule,
                    )
                    .select_from(finding)
                    .where(finding.c.status != "resolved")
                    .group_by(finding.c.rule)
                )
            )
            .mappings()
            .all()
        )
        return QualityCounts(
            total=sum(row["total"] for row in rows),
            errors=sum(row["errors"] for row in rows),
            warnings=sum(row["warnings"] for row in rows),
            info=sum(row["info"] for row in rows),
            rules=sorted(row["rule"] for row in rows),
            rule_counts={
                **dict.fromkeys((RULE, *CORE_RULES, *QUEUE_RULES), 0),
                **{row["rule"]: row["total"] for row in rows},
            },
            mode="persisted",
        ), sum(row["urgent"] for row in rows)


async def review(
    admin: AsyncConnection, source: AsyncConnection, body: ReviewUpdate, subject: str, now: datetime
) -> Finding:
    if body.status == "snoozed" and (body.snoozed_until is None or body.snoozed_until <= now):
        raise APIError(422, "invalid_input", "Snooze expiry must be in the future.")
    if (
        body.assigned_to
        and not (
            await source.execute(
                text('SELECT EXISTS(SELECT 1 FROM uranus."user" WHERE uuid=:id)'),
                {"id": body.assigned_to},
            )
        ).scalar_one()
    ):
        raise APIError(422, "invalid_input", "Unknown assignee.")
    await lock(admin)
    try:
        async with admin.begin():
            current = (
                (
                    await admin.execute(
                        select(*FINDING_COLUMNS)
                        .where(finding.c.id == body.finding_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                raise APIError(404, "finding_not_found", "Finding does not exist.")
            if current["status"] == "resolved":
                raise APIError(
                    422, "invalid_input", "A resolved finding can only reopen through recheck."
                )
            values = {
                "status": body.status,
                "reviewed_subject": subject,
                "reviewed_at": now,
                "snoozed_until": body.snoozed_until if body.status == "snoozed" else None,
                "exception_reason": body.exception_reason if body.status == "exception" else None,
            }
            if "assigned_to" in body.model_fields_set:
                values["assigned_to"] = body.assigned_to
            if "comment" in body.model_fields_set:
                values["comment"] = body.comment
            row = (
                (
                    await admin.execute(
                        update(finding)
                        .where(finding.c.id == body.finding_id)
                        .values(**values)
                        .returning(*FINDING_COLUMNS)
                    )
                )
                .mappings()
                .one()
            )
            return stored_finding(dict(row))
    finally:
        await unlock(admin)


async def spatial_stored_rows(
    admin: AsyncConnection, source: AsyncConnection, conditions: list[Any], geo_scope_wkb: bytes
) -> AsyncIterator[dict[str, Any]]:
    """Exact scan, bounded memory: server cursor + 500-row membership batches.

    Each connection has its own read-only snapshot, not a distributed snapshot. No IDs
    for the complete result set are materialized. Source uses at most five queries/batch.
    """
    query = (
        select(*FINDING_COLUMNS)
        .where(*conditions, finding.c.entity_type.in_(sorted(SPATIAL_TYPES)))
        .order_by(stored_priority_score().desc(), finding.c.id.collate("C"))
        .execution_options(yield_per=MEMBERSHIP_BATCH_SIZE)
    )
    async with admin.stream(query) as result:
        async for batch in result.mappings().partitions(MEMBERSHIP_BATCH_SIZE):
            eligible = await spatial_membership(
                source, ((row["entity_type"], row["entity_key"]) for row in batch), geo_scope_wkb
            )
            for row in batch:
                if (row["entity_type"], row["entity_key"]) in eligible:
                    yield dict(row)


async def spatial_persisted_page(
    admin: AsyncConnection,
    source: AsyncConnection,
    filters: FindingFilters,
    now: datetime,
    geo_scope_wkb: bytes,
) -> FindingPage:
    cursor_mode = filters.cursor is not None
    expected_scope = scope(filters)
    position = (
        decode(filters.cursor, FindingCursor, expected_scope)
        if filters.cursor and filters.cursor != "start"
        else None
    )
    conditions = []
    for key in ("severity", "entity_type", "entity_key", "rule", "status"):
        if (value := getattr(filters, key)) is not None:
            conditions.append(finding.c[key] == value)
    if filters.organization_id is not None:
        conditions.append(
            finding.c.metadata["finding"]["organization_id"].as_string()
            == str(filters.organization_id)
        )
    items: list[Finding] = []
    total = 0
    start = 0 if cursor_mode else (filters.page - 1) * filters.page_size
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        async for row in spatial_stored_rows(admin, source, conditions, geo_scope_wkb):
            total += 1
            if total <= start:
                continue
            # One extra eligible item suffices for cursor has_more. Continue scanning
            # identities to retain an EXACT total, but never retain the whole result.
            if len(items) >= filters.page_size + int(cursor_mode):
                continue
            item = stored_finding(row)
            if position and (-item.priority_score, item.id) <= (
                -position.priority_score,
                position.id,
            ):
                continue
            items.append(item)
    has_more = cursor_mode and len(items) > filters.page_size
    items = items[: filters.page_size]
    next_cursor = (
        encode(
            FindingCursor(
                scope=expected_scope, priority_score=items[-1].priority_score, id=items[-1].id
            )
        )
        if has_more
        else None
    )
    return FindingPage(
        items=items,
        mode="persisted",
        observed_at=now,
        cursor_pagination=CursorPagination(
            page_size=filters.page_size, next_cursor=next_cursor, has_more=has_more
        )
        if cursor_mode
        else None,
        pagination=Pagination(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            pages=(total + filters.page_size - 1) // filters.page_size,
        ),
    )


async def spatial_persisted_counts(
    admin: AsyncConnection,
    source: AsyncConnection,
    geo_scope_wkb: bytes,
) -> tuple[QualityCounts, int]:
    counts = QualityCounts(
        total=0,
        errors=0,
        warnings=0,
        info=0,
        rules=[],
        rule_counts=dict.fromkeys((RULE, *CORE_RULES, *QUEUE_RULES), 0),
        mode="persisted",
    )
    urgent = 0
    active_rules: set[str] = set()
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        async for row in spatial_stored_rows(
            admin, source, [finding.c.status != "resolved"], geo_scope_wkb
        ):
            item = stored_finding(row)
            counts.total += 1
            counts.errors += item.severity == "error"
            counts.warnings += item.severity == "warning"
            counts.info += item.severity == "info"
            counts.rule_counts[item.rule] = counts.rule_counts.get(item.rule, 0) + 1
            active_rules.add(item.rule)
            urgent += item.priority <= 2 or "published_soon" in item.priority_reasons
    counts.rules = sorted(active_rules)
    return counts, urgent
