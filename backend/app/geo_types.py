"""Minimal PostGIS DDL type. Spatial values are passed through explicit SQL functions."""

from typing import Any

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Geometry(UserDefinedType[bytes]):
    cache_ok = True

    def __init__(self, shape: str = "Geometry", srid: int | str = 4326):
        self.shape = shape
        self.srid = int(srid)

    def get_col_spec(self, **kw: Any) -> str:
        return f"geometry({self.shape},{self.srid})"


# Preserve type/SRID during admin-only Alembic comparison.
ischema_names["geometry"] = Geometry
