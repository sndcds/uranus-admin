"""Capability checked before selecting the optional source field. SELECT only."""

import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.query import ReadQuery
from app.schemas.notifications import ConfigIssue, NotificationConfig


async def source_capability(source: AsyncConnection) -> bool:
    return bool(
        (
            await source.execute(capability_query().statement, capability_query().parameters)
        ).scalar_one()
    )


async def organization_configs(
    source: AsyncConnection, organization_id: UUID | None = None
) -> list[dict[str, Any]]:
    if not await source_capability(source):
        return []
    rows: list[dict[str, Any]] = []
    after: UUID | None = None
    while True:
        page = (
            (
                await source.execute(
                    organization_config_query(after, organization_id).statement,
                    organization_config_query(after, organization_id).parameters,
                )
            )
            .mappings()
            .all()
        )
        rows.extend(dict(row) for row in page)
        if len(page) < 200:
            return rows
        after = page[-1]["uuid"]


def validate_configs(
    rows: list[dict[str, Any]],
) -> tuple[dict[UUID, NotificationConfig], list[ConfigIssue]]:
    configs = {}
    issues = []
    for row in rows:
        if row["notifications"] is None:
            continue  # No subscription is not a malformed subscription.
        try:
            configs[row["uuid"]] = NotificationConfig.model_validate(row["notifications"])
        except ValidationError:
            issues.append(ConfigIssue(organization_id=row["uuid"], organization_name=row["name"]))
            logging.getLogger("admin.notifications").warning(
                "invalid_notification_config", extra={"organization_id": str(row["uuid"])}
            )
    return configs, issues


def capability_query() -> ReadQuery:
    return ReadQuery(
        text("""
        SELECT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='uranus' AND table_name='organization'
        AND column_name='notifications' AND data_type IN ('json','jsonb'))
    """),
        {},
    )


def organization_config_query(after: UUID | None, organization_id: UUID | None) -> ReadQuery:
    return ReadQuery(
        text("""
            SELECT uuid, name, notifications FROM uranus.organization
            WHERE (CAST(:after AS uuid) IS NULL OR uuid > :after)
            AND (CAST(:organization_id AS uuid) IS NULL OR uuid=:organization_id)
            ORDER BY uuid LIMIT 200
        """),
        {"after": after, "organization_id": organization_id},
    )
