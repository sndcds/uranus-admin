"""A bound, application-owned read statement shared by runtime and inspection."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.sql import Executable


@dataclass(frozen=True)
class ReadQuery:
    statement: Executable
    parameters: dict[str, Any] = field(default_factory=dict)
