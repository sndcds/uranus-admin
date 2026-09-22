from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import (
    assignment,
    assignment_event,
    auth_account,
    auth_system_admin,
    finding,
    geocode_request,
    notification_delivery,
)
from app.errors import APIError
from app.schemas.assignments import (
    AdminOption,
    Assignment,
    AssignmentCreate,
    AssignmentLookup,
    AssignmentUpdate,
)

ACTIVE = ("open", "in_progress")


def assignment_projection() -> Any:
    return select(
        assignment,
        auth_account.c.login.label("assigned_to_login"),
    ).join(auth_account, auth_account.c.id == assignment.c.assigned_to_admin_id)


def map_assignment(row: dict[str, Any]) -> Assignment:
    return Assignment.model_validate(
        {
            **row,
            "assigned_to": {
                "id": row["assigned_to_admin_id"],
                "login": row["assigned_to_login"],
            },
        }
    )


async def admin_options(admin: AsyncConnection) -> list[AdminOption]:
    query = (
        select(auth_account.c.id, auth_account.c.login)
        .join(auth_system_admin, auth_system_admin.c.account_id == auth_account.c.id)
        .where(auth_account.c.is_active.is_(True))
        .order_by(auth_account.c.login.collate("C"), auth_account.c.id)
        .limit(200)
    )
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        rows = (await admin.execute(query)).mappings()
        return [AdminOption.model_validate(dict(row)) for row in rows]


async def require_admin(admin: AsyncConnection, account_id: UUID) -> None:
    exists = (
        await admin.execute(
            select(auth_account.c.id)
            .join(auth_system_admin, auth_system_admin.c.account_id == auth_account.c.id)
            .where(auth_account.c.id == account_id, auth_account.c.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if exists is None:
        raise APIError(
            422, "assignment_assignee_invalid", "Assignee is not an active administrator."
        )


async def task_identity(
    admin: AsyncConnection, body: AssignmentCreate
) -> tuple[str, str, str | None, str | None]:
    if body.finding_id is not None:
        row = (
            await admin.execute(
                select(finding.c.entity_type, finding.c.entity_key, finding.c.status).where(
                    finding.c.id == body.finding_id
                )
            )
        ).first()
        if row is None:
            raise APIError(404, "finding_not_found", "Finding does not exist.")
        if row.status == "resolved":
            raise APIError(422, "assignment_task_closed", "Resolved findings cannot be assigned.")
        return str(row.entity_type), str(row.entity_key), body.finding_id, None

    assert body.workflow_type is not None and body.workflow_key is not None
    try:
        key = UUID(body.workflow_key)
    except ValueError:
        raise APIError(422, "assignment_task_invalid", "Workflow task does not exist.") from None
    if body.workflow_type == "geocode_request":
        row = (
            await admin.execute(
                select(
                    geocode_request.c.entity_type,
                    geocode_request.c.entity_key,
                    geocode_request.c.status,
                ).where(geocode_request.c.id == key)
            )
        ).first()
        actionable = {"candidate", "ambiguous", "not_found", "failed"}
    else:
        row = (
            await admin.execute(
                select(
                    notification_delivery.c.organization_id,
                    notification_delivery.c.status,
                ).where(notification_delivery.c.id == key)
            )
        ).first()
        actionable = {"failed", "permanent_failure"}
    if row is None:
        raise APIError(404, "assignment_task_not_found", "Workflow task does not exist.")
    if row.status not in actionable:
        raise APIError(422, "assignment_task_closed", "Workflow task is not actionable.")
    entity_type = (
        str(row.entity_type) if body.workflow_type == "geocode_request" else "organization"
    )
    entity_key = str(
        row.entity_key if body.workflow_type == "geocode_request" else row.organization_id
    )
    assert body.entity_type is not None and body.entity_key is not None
    if body.entity_type != entity_type or body.entity_key != entity_key:
        raise APIError(
            422,
            "assignment_task_invalid",
            "Workflow entity identity does not match the durable task.",
        )
    return entity_type, entity_key, None, str(key)


async def append_event(
    admin: AsyncConnection, state: dict[str, Any], kind: str, actor: str
) -> None:
    await admin.execute(
        assignment_event.insert().values(
            id=uuid4(),
            assignment_id=state["id"],
            version=state["version"],
            kind=kind,
            occurred_at=state["updated_at"],
            actor=actor,
            assigned_to_admin_id=state["assigned_to_admin_id"],
            status=state["status"],
            due_at=state["due_at"],
            snoozed_until=state["snoozed_until"],
        )
    )


async def assignment_detail(admin: AsyncConnection, assignment_id: UUID) -> Assignment:
    row = (
        (await admin.execute(assignment_projection().where(assignment.c.id == assignment_id)))
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "assignment_not_found", "Assignment does not exist.")
    return map_assignment(dict(row))


async def active_assignment(admin: AsyncConnection, lookup: AssignmentLookup) -> Assignment | None:
    identity = (
        assignment.c.finding_id == lookup.finding_id
        if lookup.finding_id is not None
        else and_(
            assignment.c.workflow_type == lookup.workflow_type,
            assignment.c.workflow_key == lookup.workflow_key,
        )
    )
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        row = (
            (
                await admin.execute(
                    assignment_projection().where(identity, assignment.c.status.in_(ACTIVE))
                )
            )
            .mappings()
            .first()
        )
        return map_assignment(dict(row)) if row else None


async def create_assignment(
    admin: AsyncConnection, body: AssignmentCreate, actor: str
) -> Assignment:
    now = datetime.now(UTC)
    async with admin.begin():
        await require_admin(admin, body.assigned_to_admin_id)
        entity_type, entity_key, finding_id, workflow_key = await task_identity(admin, body)
        lock_key = f"assignment:{finding_id or body.workflow_type}:{workflow_key or ''}"
        await admin.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": lock_key}
        )
        identity = (
            assignment.c.finding_id == finding_id
            if finding_id is not None
            else and_(
                assignment.c.workflow_type == body.workflow_type,
                assignment.c.workflow_key == workflow_key,
            )
        )
        if (
            await admin.execute(
                select(assignment.c.id).where(identity, assignment.c.status.in_(ACTIVE))
            )
        ).scalar_one_or_none() is not None:
            raise APIError(409, "assignment_conflict", "Task already has an active assignment.")
        new_id = uuid4()
        state = {
            "id": new_id,
            "finding_id": finding_id,
            "workflow_type": body.workflow_type,
            "workflow_key": workflow_key,
            "entity_type": entity_type,
            "entity_key": entity_key,
            "assigned_to_admin_id": body.assigned_to_admin_id,
            "assigned_by_subject": actor,
            "status": body.status,
            "due_at": body.due_at,
            "snoozed_until": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "version": 1,
        }
        await admin.execute(assignment.insert().values(**state))
        await append_event(admin, state, "created", actor)
        return await assignment_detail(admin, new_id)


async def update_assignment(
    admin: AsyncConnection, assignment_id: UUID, body: AssignmentUpdate, actor: str
) -> Assignment:
    async with admin.begin():
        current = (
            (
                await admin.execute(
                    select(assignment).where(assignment.c.id == assignment_id).with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if current is None:
            raise APIError(404, "assignment_not_found", "Assignment does not exist.")
        if current["version"] != body.version:
            raise APIError(409, "assignment_conflict", "Assignment changed; reload before saving.")
        patch = body.model_dump(exclude_unset=True, exclude={"version"})
        state = {**dict(current), **patch}
        await require_admin(admin, state["assigned_to_admin_id"])
        if current["status"] in {"done", "cancelled"} and body.status == "cancelled":
            raise APIError(
                422, "assignment_task_closed", "Closed assignment cannot be cancelled again."
            )
        now = datetime.now(UTC)
        if "snoozed_until" in patch and body.snoozed_until is not None:
            if current["status"] not in ACTIVE or state["status"] not in ACTIVE:
                raise APIError(422, "assignment_task_closed", "Closed assignments cannot snooze.")
            if not now < body.snoozed_until <= now + timedelta(days=365):
                raise APIError(422, "invalid_input", "Snooze must be within the next 365 days.")
            identity = {
                "finding_id": current["finding_id"],
                "assigned_to_admin_id": state["assigned_to_admin_id"],
            }
            if current["finding_id"] is None:
                identity.update(
                    {
                        key: current[key]
                        for key in ("workflow_type", "workflow_key", "entity_type", "entity_key")
                    }
                )
            await task_identity(admin, AssignmentCreate.model_validate(identity))
        # Completion clears organizational snooze in the same audited snapshot.
        if state["status"] not in ACTIVE:
            patch["snoozed_until"] = None
        if all(current[key] == value for key, value in patch.items()):
            return await assignment_detail(admin, assignment_id)
        now = max(now, current["updated_at"])
        kind = "updated"
        completed_at = current["completed_at"]
        if state["status"] != current["status"]:
            if state["status"] in {"done", "cancelled"}:
                kind = "completed" if state["status"] == "done" else "cancelled"
                completed_at = now
            elif current["status"] in {"done", "cancelled"}:
                kind = "reopened"
                completed_at = None
        values = {
            **patch,
            "completed_at": completed_at,
            "updated_at": now,
            "version": current["version"] + 1,
        }
        await admin.execute(
            assignment.update().where(assignment.c.id == assignment_id).values(**values)
        )
        await append_event(admin, {**dict(current), **values}, kind, actor)
        return await assignment_detail(admin, assignment_id)
