"""Reuse canonical record images for a bounded findings page, never per finding."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.activity_previews import PUBLIC_API, activity_previews
from app.schemas.finding import Finding

IMAGE_TYPES = frozenset({"organization", "venue", "event", "event_date", "user", "image"})


def image_identities(items: list[Finding], settings: Settings) -> list[dict[str, str]]:
    if settings.uranus_api_url.rstrip("/") != PUBLIC_API:
        return []
    identities: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        if item.entity_type not in IMAGE_TYPES:
            continue
        try:
            key = str(UUID(item.entity_key))
        except ValueError:
            continue
        identities[(item.entity_type, key)] = {"entity_type": item.entity_type, "entity_key": key}
    return list(identities.values())


async def enrich_images(
    connection: AsyncConnection, settings: Settings, items: list[Finding], now: datetime
) -> None:
    identities = image_identities(items, settings)
    if not identities:
        return
    previews = await activity_previews(connection, settings, identities, now)
    for item in items:
        if item.entity_type not in IMAGE_TYPES:
            continue
        try:
            key = str(UUID(item.entity_key))
        except ValueError:
            continue
        # Do not copy unrelated preview data (email, coordinates, public links or status).
        item.image_url = previews.get((item.entity_type, key), {}).get("image_url")
