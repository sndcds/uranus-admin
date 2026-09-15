"""Structured targets; emitted only when the corresponding UI actually exists."""

from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, computed_field, model_validator


class Action(BaseModel):
    type: Literal["view"] = "view"
    route: Literal["activity", "partner_requests", "team_invitations", "user_activation"]
    entity_type: (
        Literal[
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
        | None
    ) = None
    entity_key: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def valid_target(self) -> "Action":
        if self.route == "activity" and self.entity_type is None:
            raise ValueError("Activity actions require an explicit entity type")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def href(self) -> str:
        path = "/activity" if self.route == "activity" else f"/queues/{self.route}"
        suffix = f"&entity_type={self.entity_type}" if self.route == "activity" else ""
        return f"{path}?entity_key={quote(self.entity_key, safe='')}{suffix}"
