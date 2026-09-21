"""Version 1: text JSON only, no query parameters or arbitrary bind parameters."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    v: Literal[1]
    request_id: UUID


class Execute(Message):
    type: Literal["execute"]
    sql: str = Field(min_length=1, max_length=32768, repr=False)
    params: dict[str, str] = Field(default_factory=dict, max_length=0, repr=False)
    row_limit: int = Field(default=50, ge=1, le=500)


class Cancel(Message):
    type: Literal["cancel"]


class Ack(Message):
    type: Literal["ack"]
    batch: int = Field(ge=1, le=500)


client_message: TypeAdapter[Execute | Cancel | Ack] = TypeAdapter(
    Annotated[Execute | Cancel | Ack, Field(discriminator="type")]
)
