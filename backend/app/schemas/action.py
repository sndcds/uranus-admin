"""Structured targets; emitted only when the corresponding UI actually exists."""

from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, computed_field


class Action(BaseModel):
    type: Literal["view"] = "view"
    route: Literal["activity", "partner_requests", "team_invitations", "user_activation"]
    entity_key: str = Field(min_length=1, max_length=1024)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def href(self) -> str:
        path = "/activity" if self.route == "activity" else f"/queues/{self.route}"
        return f"{path}?entity_key={quote(self.entity_key, safe='')}"
