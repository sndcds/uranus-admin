"""Render server-owned registered copy SQL without changing its source relations."""

from pglast import parse_sql
from pglast.stream import RawStream


def initial_sql(copy_sql: str) -> str:
    return str(RawStream()(parse_sql(copy_sql))) + ";"  # type: ignore[no-untyped-call]
