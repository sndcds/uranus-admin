"""PostgreSQL AST gate, secondary to the provisioned database boundary."""

import json
from pathlib import Path
from typing import Any

from pglast.parser import parse_sql_json

POLICY = json.loads(Path(__file__).with_name("function_policy.json").read_text())
MAX_SQL_BYTES = 32768
# Additional transport privacy guard: all console sessions share one DB identity.
# PostgreSQL activity functions can expose another console user's SQL; SQL/XML
# wrappers and text-search helpers can execute SQL strings outside this AST.
# Deny whole names, including overloads; do not attempt to parse SQL in literals.
PRIVACY_NAMES = frozenset({"ts_stat", "ts_rewrite"})
PRIVACY_PREFIXES = (
    "pg_stat_get_",
    "query_to_",
    "table_to_",
    "schema_to_",
    "database_to_",
    "cursor_to_",
)


class ConsoleError(Exception):
    def __init__(self, code: str, position: int | None = None) -> None:
        self.code = code
        self.position = position
        super().__init__(code)


def denied_function(name: str) -> bool:
    name = name.lower()
    return (
        name in PRIVACY_NAMES
        or name in POLICY["names"]
        or any(name.startswith(p) for p in (*POLICY["prefixes"], *PRIVACY_PREFIXES))
    )


def validate_sql(sql: str) -> None:
    if not sql.strip() or len(sql.encode()) > MAX_SQL_BYTES:
        raise ConsoleError("invalid_sql")
    try:
        tree = json.loads(parse_sql_json(sql))
    except Exception:
        raise ConsoleError("syntax_error") from None
    statements = tree.get("stmts", [])
    if len(statements) != 1 or set(statements[0]["stmt"]) != {"SelectStmt"}:
        raise ConsoleError("query_only")

    def visit(node: Any, depth: int = 0, ctes: frozenset[str] = frozenset()) -> None:
        if depth > 100:
            raise ConsoleError("query_too_complex")
        if isinstance(node, list):
            for value in node:
                visit(value, depth + 1, ctes)
        elif isinstance(node, dict):
            for kind, value in node.items():
                if kind.endswith("Stmt") and kind != "SelectStmt":
                    raise ConsoleError("query_only")
                if kind in {"IntoClause", "intoClause", "LockingClause", "ParamRef"}:
                    raise ConsoleError("query_only")
                if kind == "SelectStmt":
                    # PostgreSQL CTE visibility is lexical, and non-recursive WITH
                    # exposes only preceding CTEs inside each definition.
                    clause = value.get("withClause", {})
                    definitions = clause.get("ctes", [])
                    visible = ctes
                    if clause.get("recursive"):
                        visible |= frozenset(c["CommonTableExpr"]["ctename"] for c in definitions)
                    for definition in definitions:
                        visit(definition, depth + 1, visible)
                        visible |= {definition["CommonTableExpr"]["ctename"]}
                    for field, child in value.items():
                        if field != "withClause":
                            visit({field: child}, depth + 1, visible)
                    continue
                if kind == "RangeVar":
                    schema = value.get("schemaname")
                    name = value["relname"]
                    # pg_catalog precedes uranus in search_path. A lexical CTE
                    # may shadow a catalog name, but cannot authorize its siblings.
                    if (
                        value.get("catalogname")
                        or schema not in {None, "uranus"}
                        or schema is None
                        and name.startswith("pg_")
                        and name not in ctes
                    ):
                        raise ConsoleError("permission_denied")
                if kind == "FuncCall":
                    name = value["funcname"][-1]["String"]["sval"]
                    if denied_function(name):
                        raise ConsoleError("function_denied")
                visit(value, depth + 1, ctes)

    visit(statements)
