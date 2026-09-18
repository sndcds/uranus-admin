"""Shared read-only revalidation for workers and explicit admin retry requests."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin_tables import finding
from app.config import Settings
from app.repositories.quality_sources import load_sources
from app.schemas.notifications import NotificationConfig
from app.services.notifications.candidates import Candidate, detect
from app.services.notifications.config import (
    organization_configs,
    source_capability,
    validate_configs,
)

LOG = logging.getLogger("admin.notifications")


async def collect(
    source: AsyncEngine,
    admin: AsyncEngine,
    settings: Settings,
    now: datetime,
    organization_id: UUID | None = None,
) -> tuple[bool, dict[UUID, NotificationConfig], list[Candidate]]:
    async with source.connect() as reader, reader.begin():
        await reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        capability = await source_capability(reader)
        if not capability:
            LOG.warning("notification_source_capability_missing")
            return False, {}, []
        configs, _ = validate_configs(await organization_configs(reader, organization_id))
        sources = await load_sources(reader, organization_id)
        async with admin.connect() as writer, writer.begin():
            reviews = dict(
                (
                    await writer.execute(
                        select(finding.c.id, finding.c.status).where(
                            finding.c.metadata["finding"]["organization_id"].as_string()
                            == str(organization_id)
                        )
                        if organization_id is not None
                        else select(finding.c.id, finding.c.status)
                    )
                )
                .tuples()
                .all()
            )
        return True, configs, detect(sources, configs, reviews, settings, now)


def refresh_rows(rows: list[dict[str, Any]], fresh: list[Candidate]) -> list[dict[str, Any]]:
    fresh_map = {candidate.dedupe_key: candidate for candidate in fresh}
    result = []
    for old in rows:
        row = dict(old)
        item = fresh_map.get(row["dedupe_key"])
        row["status"] = item.status if item else "suppressed"
        if item:
            row["payload"] = item.payload.model_dump(mode="json")
            row["payload"]["episode"] = old["payload"].get("episode", 1)
        result.append(row)
    return result
