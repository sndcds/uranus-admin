import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import check_run, finding
from app.config import Settings
from app.errors import APIError
from app.schemas.checks import CheckRun, ReviewUpdate
from app.schemas.finding import Finding, FindingFilters, FindingPage, Severity
from app.services.quality.core import RuleResult
from app.services.quality.engine import findings_page, scan
from app.services.quality.priority import priority_details

# Session lock survives the initial committed 'running' row. Scans and reviews serialize.
LOCK_KEY = 723114905

# Explicit labels keep result mappings independent of physical legacy column names.
FINDING_COLUMNS = tuple(column.label(column.key) for column in finding.c)


async def lock(connection: AsyncConnection) -> None:
    acquired = (
        await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
    ).scalar_one()
    await connection.commit()
    if not acquired:
        raise APIError(409, "check_run_conflict", "A check or review is already in progress.")


async def unlock(connection: AsyncConnection) -> None:
    if connection.in_transaction():
        await connection.rollback()
    await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
    await connection.commit()


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


async def run_check(
    source: AsyncConnection, admin: AsyncConnection, settings: Settings
) -> CheckRun:
    await lock(admin)
    run_id = uuid4()
    started = datetime.now(UTC)
    try:
        async with admin.begin():
            # An interrupted process left running rows. Lock ownership proves no active peer run.
            await admin.execute(
                update(check_run)
                .where(check_run.c.status == "running")
                .values(
                    status="failed",
                    finished_at=started,
                    error_message="Check interrupted; no automatic resolution.",
                )
            )
            await admin.execute(
                insert(check_run).values(id=run_id, started_at=started, status="running")
            )
        try:
            results = await scan(source, settings, started)
            if not results or not all(result.success for result in results):
                raise RuntimeError("Incomplete scan")
            finished = datetime.now(UTC)
            async with admin.begin():
                await persist_results(admin, results, finished)
                await admin.execute(
                    update(check_run)
                    .where(check_run.c.id == run_id)
                    .values(
                        status="success",
                        finished_at=finished,
                        rule_count=len(results),
                        finding_count=sum(len(result.findings) for result in results),
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
        except Exception as exc:
            logging.getLogger("admin.checks").error(
                "check_failed", extra={"error_type": type(exc).__name__}
            )
            if admin.in_transaction():
                await admin.rollback()
            async with admin.begin():
                await admin.execute(
                    update(check_run)
                    .where(check_run.c.id == run_id)
                    .values(
                        status="failed",
                        finished_at=datetime.now(UTC),
                        error_message="Check failed; no findings resolved.",
                    )
                )
        async with admin.begin():
            row = (
                (await admin.execute(select(check_run).where(check_run.c.id == run_id)))
                .mappings()
                .one()
            )
            return CheckRun.model_validate(dict(row))
    finally:
        await unlock(admin)


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


async def persisted_page(
    admin: AsyncConnection, filters: FindingFilters, now: datetime
) -> FindingPage:
    async with admin.begin():
        items = [
            stored_finding(dict(row))
            for row in (await admin.execute(select(*FINDING_COLUMNS))).mappings()
        ]
    result = findings_page(items, filters, now)
    result.mode = "persisted"
    return result


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
