"""Shared execution response primitives, independent of Planner wire versions."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("blank_string")
    return value


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


Query = Annotated[str, StringConstraints(min_length=1, max_length=2000), AfterValidator(nonblank)]
Slot = Annotated[str, StringConstraints(min_length=1, max_length=160), AfterValidator(nonblank)]
