"""Read-only system-admin notification inspection and previews. GET never schedules mail."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.admin_database import AdminConnectionDep
from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.database import ConnectionDep, SettingsDep
from app.errors import APIError
from app.repositories.notifications import local_day
from app.schemas.finding import Pagination
from app.schemas.notifications import (
    DeliveryDetail,
    Locale,
    NotificationCounts,
    NotificationDelivery,
    NotificationDetail,
    NotificationHealth,
    NotificationPage,
    NotificationPreview,
    NotificationStatus,
    NotificationSummary,
    NotificationType,
)
from app.services.notifications.config import (
    organization_configs,
    source_capability,
    validate_configs,
)
from app.services.notifications.rendering import render

router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=NotificationPage)
async def notifications(
    admin: AdminConnectionDep,
    source: ConnectionDep,
    settings: SettingsDep,
    status: NotificationStatus | None = None,
    notification_type: NotificationType | None = None,
    organization_id: UUID | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationPage:
    from datetime import timedelta

    now = datetime.now(UTC)
    capability = await source_capability(source)
    _, issues = validate_configs(await organization_configs(source))
    conditions = []
    for column, value in (
        (n.c.status, status),
        (n.c.notification_type, notification_type),
        (n.c.organization_id, organization_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if days:
        conditions.append(n.c.last_detected_at >= now - timedelta(days=days))
    async with admin.begin():
        total = (
            await admin.execute(select(func.count()).select_from(n).where(*conditions))
        ).scalar_one()
        rows = (
            await admin.execute(
                select(n)
                .where(*conditions)
                .order_by(n.c.last_detected_at.desc(), n.c.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).mappings()
        items = [NotificationSummary.model_validate(dict(row)) for row in rows]
        active = (
            await admin.execute(select(func.count()).select_from(n).where(n.c.status == "active"))
        ).scalar_one()
        start, end = local_day(now, settings.admin_timezone)
        queued = (
            await admin.execute(
                select(func.count()).select_from(d).where(d.c.status.in_(["queued", "sending"]))
            )
        ).scalar_one()
        sent = (
            await admin.execute(
                select(func.count())
                .select_from(d)
                .where(d.c.status == "sent", d.c.sent_at >= start, d.c.sent_at < end)
            )
        ).scalar_one()
        failed = (
            await admin.execute(
                select(func.count())
                .select_from(d)
                .where(d.c.status.in_(["failed", "permanent_failure"]))
            )
        ).scalar_one()
    return NotificationPage(
        items=items,
        pagination=Pagination(
            page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size
        ),
        summary=NotificationCounts(active=active, queued=queued, sent_today=sent, failed=failed),
        health=NotificationHealth(
            delivery_enabled=settings.notifications_delivery_enabled,
            source_capability=capability,
            config_issues=issues,
        ),
    )


@router.get("/notifications/{notification_id}", response_model=NotificationDetail)
async def detail(
    notification_id: UUID, admin: AdminConnectionDep, settings: SettingsDep
) -> NotificationDetail:
    async with admin.begin():
        row = (
            (await admin.execute(select(n).where(n.c.id == notification_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise APIError(404, "not_found", "Notification not found.")
        deliveries = (
            await admin.execute(
                select(d)
                .join(di, di.c.delivery_id == d.c.id)
                .where(di.c.notification_id == notification_id)
                .order_by(d.c.created_at.desc(), d.c.id)
            )
        ).mappings()
        return NotificationDetail(
            **dict(row),
            deliveries=[NotificationDelivery.model_validate(dict(r)) for r in deliveries],
            delivery_enabled=settings.notifications_delivery_enabled,
        )


@router.get("/notifications/{notification_id}/preview", response_model=NotificationPreview)
async def preview(
    notification_id: UUID, admin: AdminConnectionDep, settings: SettingsDep, locale: Locale = "de"
) -> NotificationPreview:
    item = await detail(notification_id, admin, settings)
    # Preview historical payloads deliberately; never implies current send eligibility.
    if item.payload.rule is None and (
        item.payload.event_status is None
        or item.payload.next_date is None
        or item.payload.days_until is None
    ):
        raise APIError(422, "invalid_input", "No event email is available for this state.")
    return render([item.payload], locale, settings, [item.id])


@router.get("/notification-deliveries/{delivery_id}", response_model=DeliveryDetail)
async def delivery_detail(delivery_id: UUID, admin: AdminConnectionDep) -> DeliveryDetail:
    async with admin.begin():
        row = (await admin.execute(select(d).where(d.c.id == delivery_id))).mappings().one_or_none()
        if row is None:
            raise APIError(404, "not_found", "Delivery not found.")
        items = (
            await admin.execute(
                select(n)
                .join(di, di.c.notification_id == n.c.id)
                .where(di.c.delivery_id == delivery_id)
                .order_by(n.c.id)
            )
        ).mappings()
        return DeliveryDetail(
            **dict(row), notifications=[NotificationSummary.model_validate(dict(r)) for r in items]
        )
