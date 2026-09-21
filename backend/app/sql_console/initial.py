"""Adapt only server-owned registered copy SQL, never client SQL or DOM text."""

from pglast import parse_sql
from pglast.stream import RawStream
from pglast.visitors import Visitor

from app.sql_console.policy import POLICY


class ConsoleRelations(Visitor):
    def visit_RangeVar(self, ancestors, node):  # type: ignore[no-untyped-def]
        if node.schemaname == "uranus" and node.relname in POLICY["views"]:
            node.schemaname = "uranus_console"


def initial_sql(copy_sql: str) -> str:
    tree = parse_sql(copy_sql)
    ConsoleRelations()(tree)
    return str(RawStream()(tree)) + ";"  # type: ignore[no-untyped-call]
