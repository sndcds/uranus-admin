"""Versioned, validated keyset cursors. Opaque navigation, never authorization."""

import base64
import hashlib
import json
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.errors import APIError


class CursorPagination(BaseModel):
    page_size: int
    next_cursor: str | None
    has_more: bool


class ActivityCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    endpoint: Literal["activity"] = "activity"
    scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    entity_type: Literal[
        "organization",
        "venue",
        "space",
        "event",
        "event_date",
        "user",
        "partner_request",
        "team_membership",
        "image",
    ]
    entity_key: str = Field(min_length=1, max_length=1024)
    created_at: AwareDatetime | None
    from_at: AwareDatetime | None
    to_at: AwareDatetime | None


class FindingCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    endpoint: Literal["findings"] = "findings"
    scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    priority_score: int = Field(ge=0, le=2**31 - 1)
    id: str = Field(min_length=1, max_length=8192)


def scope(filters: BaseModel, **extra: Any) -> str:
    values = filters.model_dump(mode="json", exclude={"page", "page_size", "cursor"})
    values.update(extra)
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def encode(value: BaseModel) -> str:
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")


def decode[T: (ActivityCursor, FindingCursor)](raw: str, model: type[T], expected_scope: str) -> T:
    try:
        if not raw or len(raw) > 16384:
            raise ValueError()
        data = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        result = model.model_validate_json(data)
        identity = result.entity_key if isinstance(result, ActivityCursor) else result.id
        if chr(0) in identity:
            raise ValueError()
        if (
            isinstance(result, ActivityCursor)
            and result.from_at
            and result.to_at
            and result.from_at >= result.to_at
        ):
            raise ValueError()
        if result.scope != expected_scope:
            raise ValueError()
        return result
    except (ValueError, ValidationError):
        raise APIError(422, "invalid_input", "Invalid cursor for these filters.") from None
