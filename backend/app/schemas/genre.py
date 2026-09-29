"""Canonical source genre identity; genre 0 means no assignment."""

from typing import Annotated

from pydantic import AfterValidator, Field


def validate_genre_key(value: str) -> str:
    type_id, genre_id = (int(part) for part in value.split(":"))
    if (
        not all(-2147483648 <= part <= 2147483647 for part in (type_id, genre_id))
        or genre_id == 0
        or value != f"{type_id}:{genre_id}"
    ):
        raise ValueError("invalid_genre_key")
    return value


GenreKey = Annotated[
    str,
    Field(max_length=23, pattern=r"^-?(0|[1-9][0-9]*):-?(0|[1-9][0-9]*)$"),
    AfterValidator(validate_genre_key),
]
