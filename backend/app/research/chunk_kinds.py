"""Canonical public chunk kinds shared by index and response contracts."""

from typing import Literal

Kind = Literal[
    "content",
    "participation",
    "accessibility",
    "tickets",
    "additional",
    "facilities",
    "location_context",
    "activities",
    "categories",
]
