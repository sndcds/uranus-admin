from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import record_mark as marks
from app.admin_tables import record_mark_event as events
from app.errors import APIError
from app.repositories.activity import ACTIVITY_SQL
from app.repositories.query import ReadQuery
from app.schemas.finding import Pagination
from app.schemas.marks import Mark, MarkCreate, MarkDetail, MarkFilters, MarkPage, MarkUpdate
from app.services.quality.core import entity_key


async def source_name(source: AsyncConnection, body: MarkCreate) -> str:
    """Verify the exact source identity, including records without timestamps."""
    params = {"kind": body.entity_type, "key": body.entity_key}
    if body.entity_type in {"license", "event_link"}:
        sql = (
            "SELECT key AS entity_name FROM uranus.license WHERE key=:key"
            if body.entity_type == "license"
            else "SELECT id::text AS entity_name FROM uranus.event_link WHERE id::text=:key"
        )
    elif body.entity_type == "image_link":
        parts = body.entity_key.split(":")
        if len(parts) != 4 or parts[0] != "image-link":
            raise APIError(404, "record_not_found", "Source record not found.")
        values = dict(
            zip(("context", "context_uuid", "identifier"), map(unquote, parts[1:]), strict=True)
        )
        if entity_key("image_link", values) != body.entity_key:
            raise APIError(404, "record_not_found", "Source record not found.")
        row = (
            await source.execute(
                text(
                    "SELECT identifier FROM uranus.pluto_image_link WHERE context=:context "
                    "AND context_uuid::text=:context_uuid AND identifier=:identifier"
                ),
                values,
            )
        ).first()
        if row is None:
            raise APIError(404, "record_not_found", "Source record not found.")
        return body.entity_key
    else:
        sql = (
            f"SELECT entity_name FROM ({ACTIVITY_SQL}) a "
            "WHERE entity_type=:kind AND entity_key=:key"
        )
    row = (await source.execute(text(sql), params)).first()
    if row is None:
        raise APIError(404, "record_not_found", "Source record not found.")
    return str(row[0] or body.entity_key)


async def detail_in_transaction(admin: AsyncConnection, mark_id: UUID) -> MarkDetail:
    row = (await admin.execute(mark_detail_query(mark_id))).mappings().first()
    if row is None:
        raise APIError(404, "mark_not_found", "Mark not found.")
    history = (await admin.execute(mark_events_query(mark_id))).mappings()
    return MarkDetail.model_validate({**dict(row), "events": [dict(event) for event in history]})


async def append_event(
    admin: AsyncConnection, state: dict[str, Any], kind: str, author: str, note: str | None
) -> None:
    await admin.execute(
        events.insert().values(
            id=uuid4(),
            mark_id=state["id"],
            version=state["version"],
            kind=kind,
            author=author,
            created_at=state["updated_at"],
            note=note,
            **{key: state[key] for key in ("status", "reasons", "reason_detail", "urgency")},
        )
    )


async def create_mark(
    admin: AsyncConnection, source: AsyncConnection, body: MarkCreate, author: str
) -> MarkDetail:
    name = await source_name(source, body)
    now = datetime.now(UTC)
    state = dict(
        id=uuid4(),
        **body.model_dump(exclude={"note"}),
        entity_name=name,
        status="open",
        version=1,
        created_at=now,
        created_by=author,
        updated_at=now,
        completed_at=None,
        completed_by=None,
    )
    async with admin.begin():
        await admin.execute(marks.insert().values(**state))
        await append_event(admin, state, "created", author, body.note)
        return await detail_in_transaction(admin, state["id"])


async def update_mark(
    admin: AsyncConnection, mark_id: UUID, body: MarkUpdate, author: str
) -> MarkDetail:
    async with admin.begin():
        row = (
            (await admin.execute(select(marks).where(marks.c.id == mark_id).with_for_update()))
            .mappings()
            .first()
        )
        if row is None:
            raise APIError(404, "mark_not_found", "Mark not found.")
        if row["version"] != body.version:
            raise APIError(409, "mark_conflict", "Mark changed; reload before saving.")
        changes = body.model_dump(exclude={"note", "version"})
        if all(row[key] == value for key, value in changes.items()) and not body.note:
            return await detail_in_transaction(admin, mark_id)
        now = max(datetime.now(UTC), row["updated_at"])
        kind = "updated"
        if row["status"] != "done" and body.status == "done":
            kind = "completed"
            changes.update(completed_at=now, completed_by=author)
        elif row["status"] == "done" and body.status != "done":
            kind = "reopened"
            changes.update(completed_at=None, completed_by=None)
        changes.update(version=row["version"] + 1, updated_at=now)
        await admin.execute(marks.update().where(marks.c.id == mark_id).values(**changes))
        await append_event(admin, {**dict(row), **changes}, kind, author, body.note)
        return await detail_in_transaction(admin, mark_id)


def mark_queries(filters: MarkFilters) -> dict[str, ReadQuery]:
    conditions = []
    for field in ("entity_type", "entity_key", "urgency"):
        if (value := getattr(filters, field)) is not None:
            conditions.append(marks.c[field] == value)
    if filters.status == "active":
        conditions.append(marks.c.status != "done")
    elif filters.status != "all":
        conditions.append(marks.c.status == filters.status)
    if filters.reason:
        conditions.append(marks.c.reasons.contains([filters.reason]))
    query = select(marks).where(*conditions)
    if filters.sort == "urgency":
        query = query.order_by(
            case((marks.c.urgency == "urgent", 0), (marks.c.urgency == "high", 1), else_=2)
        )
    query = query.order_by(marks.c.created_at.desc(), marks.c.id)
    return {
        "count": ReadQuery(select(func.count()).select_from(marks).where(*conditions)),
        "records": ReadQuery(
            query.limit(filters.page_size).offset((filters.page - 1) * filters.page_size)
        ),
    }


async def mark_page(admin: AsyncConnection, filters: MarkFilters) -> MarkPage:
    queries = mark_queries(filters)
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        total = int((await admin.execute(queries["count"].statement)).scalar_one())
        rows = (await admin.execute(queries["records"].statement)).mappings()
        return MarkPage(
            items=[Mark.model_validate(dict(row)) for row in rows],
            pagination=Pagination(
                page=filters.page,
                page_size=filters.page_size,
                total=total,
                pages=(total + filters.page_size - 1) // filters.page_size,
            ),
        )


def mark_detail_query(mark_id: UUID) -> Any:
    return select(marks).where(marks.c.id == mark_id)


def mark_events_query(mark_id: UUID) -> Any:
    return select(events).where(events.c.mark_id == mark_id).order_by(events.c.version)
