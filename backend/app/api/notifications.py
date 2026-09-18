"""System-admin inspection and explicit queue-only retry. GET never schedules mail."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.admin_database import AdminConnectionDep
from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.auth.service import require_origin
from app.database import ConnectionDep, SettingsDep
from app.errors import APIError
from app.repositories.notifications import local_day
from app.schemas.finding import Pagination
from app.schemas.notifications import (
    DeliveryDetail,
    DeliveryKind,
    DeliveryListItem,
    DeliveryPage,
    DeliveryStatus,
    Locale,
    NotificationCounts,
    NotificationDelivery,
    NotificationDetail,
    NotificationHealth,
    NotificationPage,
    NotificationPreview,
    NotificationRetryResponse,
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
from app.services.notifications.retry import enqueue_retry

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
        temporary = (
            await admin.execute(select(func.count()).select_from(d).where(d.c.status == "failed"))
        ).scalar_one()
    return NotificationPage(
        items=items,
        pagination=Pagination(
            page=page, page_size=page_size, total=total, pages=(total + page_size - 1) // page_size
        ),
        summary=NotificationCounts(
            active=active,
            queued=queued,
            sent_today=sent,
            failed=failed,
            temporary_failed=temporary,
            permanent_failed=failed - temporary,
        ),
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
            raise APIError(404, "notification_delivery_not_found", "Delivery not found.")
        items = (
            await admin.execute(
                select(n)
                .join(di, di.c.notification_id == n.c.id)
                .where(di.c.delivery_id == delivery_id)
                .order_by(n.c.id)
            )
        ).mappings()
        retries = (
            await admin.execute(
                select(d)
                .where(d.c.retry_of_delivery_id == delivery_id)
                .order_by(d.c.created_at, d.c.id)
            )
        ).mappings()
        return DeliveryDetail(
            retries=[NotificationDelivery.model_validate(dict(r)) for r in retries],
            **dict(row),
            notifications=[NotificationSummary.model_validate(dict(r)) for r in items],
        )


@router.get("/notification-deliveries", response_model=DeliveryPage)
async def deliveries(
    admin: AdminConnectionDep,
    settings: SettingsDep,
    status: DeliveryStatus | None = None,
    organization_id: UUID | None = None,
    delivery_kind: DeliveryKind | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DeliveryPage:
    conditions = []
    for column, value in (
        (d.c.status, status),
        (d.c.organization_id, organization_id),
        (d.c.delivery_kind, delivery_kind),
    ):
        if value is not None:
            conditions.append(column == value)
    if days:
        conditions.append(d.c.created_at >= datetime.now(UTC) - timedelta(days=days))
    # Audit name comes from the original mail snapshot; no source or per-row queries.
    name = d.c.snapshot["payloads"][0]["organization_name"].as_string()
    async with admin.begin():
        total = (
            await admin.execute(select(func.count()).select_from(d).where(*conditions))
        ).scalar_one()
        rows = (
            await admin.execute(
                select(d, func.coalesce(name, "—").label("organization_name"))
                .where(*conditions)
                .order_by(d.c.created_at.desc(), d.c.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).mappings()
        return DeliveryPage(
            items=[DeliveryListItem.model_validate(dict(r)) for r in rows],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total,
                pages=(total + page_size - 1) // page_size,
            ),
            delivery_enabled=settings.notifications_delivery_enabled,
        )


@router.post(
    "/notification-deliveries/{delivery_id}/retry",
    response_model=NotificationRetryResponse,
    status_code=201,
)
async def retry_delivery(
    principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
    delivery_id: UUID,
    request: Request,
    admin: AdminConnectionDep,
    settings: SettingsDep,
) -> NotificationRetryResponse:
    # Also enforce the exact Origin/CSRF boundary for bearer and development credentials.
    require_origin(request, settings)
    if request.query_params:
        raise APIError(422, "invalid_input", "Retry accepts no overrides.")
    # No body contract: reject the first nonempty chunk without buffering arbitrary input.
    async for chunk in request.stream():
        if chunk:
            raise APIError(422, "invalid_input", "Retry accepts no body.")
    result = await enqueue_retry(
        admin, request.app.state.engine, delivery_id, settings, datetime.now(UTC)
    )
    logging.getLogger("admin.notifications").info(
        "notification_manual_retry",
        extra={
            "delivery_id": str(result.delivery_id),
            "retry_of_delivery_id": str(delivery_id),
            "actor_subject": principal.subject,
        },
    )
    return result
