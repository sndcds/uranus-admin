"""Compile the registered runtime statement; values never become identifiers."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, JSON, LargeBinary, String, bindparam, literal, select, text
from sqlalchemy.dialects.postgresql import dialect as PGDialect
from sqlalchemy.dialects.postgresql.base import PGCompiler
from sqlalchemy.sql import Executable, Select
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.types import NullType

from app.repositories.query import ReadQuery
from app.sql_diagnostics.registry import SENSITIVE_FIELDS
from app.sql_diagnostics.render import json_value

# Opaque JSON/mail/error payloads can contain arbitrary nested private data. The
# provenance inspection uses a documented safe projection of the runtime SELECT.
OPAQUE_COLUMNS = frozenset(
    {"metadata", "payload", "snapshot", "body_html", "body_text", "error", "error_message"}
)


class InspectionCompiler(PGCompiler):
    def render_literal_value(self, value: Any, type_: Any) -> str:
        render_value: Callable[[Any, Any], str] = super().render_literal_value
        if isinstance(type_, ARRAY):
            # PostgreSQL otherwise infers ARRAY['uuid'] as text[], even though
            # the bound runtime parameter is uuid[]. Preserve that exact type.
            return (
                render_value(value, type_)
                + "::"
                + self.dialect.type_compiler_instance.process(type_)
            )
        if isinstance(type_, JSON):
            return render_value(json.dumps(value), String()) + "::jsonb"
        if isinstance(value, bytes):
            return "decode(" + render_value(value.hex(), String()) + ", 'hex')"
        return render_value(value, type_)


def dialect() -> Any:
    result = PGDialect(paramstyle="named")  # type: ignore[no-untyped-call]
    result._backslash_escapes = False
    result.statement_compiler = InspectionCompiler
    return result


def parameter_type(value: Any) -> Any:
    if value is None:
        return NullType()
    if type(value) in (str, int, bool, float, UUID, date, datetime, time, Decimal):
        return literal(value).type
    if type(value) is bytes:
        return LargeBinary()
    if isinstance(value, (list, tuple)):
        sample = next((item for item in value if item is not None), None)
        return ARRAY(parameter_type(sample) if sample is not None else String())
    raise ValueError("Unsupported registered parameter type")


def parameter_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, (tuple, list)):
        return [parameter_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): parameter_json(item) for key, item in value.items()}
    return json_value(value)


def select_only(sql: str) -> None:
    # This is an additional invariant for code-owned statements, not a SQL console
    # parser or an authorization boundary. Client SQL never reaches this function.
    scrubbed = re.sub(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S
    )
    words = re.findall(r"\b[A-Za-z_]+\b", scrubbed.upper())
    if not words or words[0] not in {"SELECT", "WITH"} or ";" in scrubbed:
        raise ValueError("Expected one registered SELECT")
    if set(words) & {
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "TRUNCATE",
        "ALTER",
        "CREATE",
        "DROP",
        "GRANT",
        "REVOKE",
        "COPY",
        "CALL",
        "DO",
        "SET",
        "INTO",
    }:
        raise ValueError("Non-read operation in registered query")


@dataclass(frozen=True)
class RenderedQuery:
    query: ReadQuery
    sql: str
    copy_sql: str
    parameters: dict[str, Any]
    columns: tuple[str, ...]
    projected: bool


def render(
    query: ReadQuery, columns: tuple[str, ...] = (), *, template: bool = False
) -> RenderedQuery:
    statement = query.statement
    projected = False
    if isinstance(statement, Select):
        safe = [
            column
            for column in statement.selected_columns
            if column.key not in SENSITIVE_FIELDS | OPAQUE_COLUMNS
            and not isinstance(column.type, JSON)
        ]
        projected = len(safe) != len(statement.selected_columns)
        if projected:
            statement = statement.with_only_columns(*safe, maintain_column_froms=True)
        columns = tuple(str(column.key) for column in statement.selected_columns)
    elif isinstance(statement, TextClause):
        statement = statement.bindparams(
            *[
                bindparam(
                    name,
                    value=query.parameters[name],
                    type_=NullType()
                    if template and query.parameters[name] == []
                    else parameter_type(query.parameters[name]),
                )
                for name in statement._bindparams
                if name in query.parameters
            ]
        )
    else:
        raise ValueError("Unsupported registered statement")
    if isinstance(statement, TextClause) and not columns:
        columns = projection_columns(statement.text)
    if set(columns) & SENSITIVE_FIELDS or not columns:
        raise ValueError("Unsafe or missing registered projection")
    compiled = statement.compile(
        dialect=dialect(), compile_kwargs={"render_postcompile": not template}
    )
    if isinstance(statement, Select):
        columns = tuple(item.keyname for item in compiled._result_columns)
    sql = str(compiled)
    select_only(sql)
    copied = (
        ""
        if template
        else str(statement.compile(dialect=dialect(), compile_kwargs={"literal_binds": True})) + ";"
    )
    return RenderedQuery(
        ReadQuery(statement, query.parameters),
        sql,
        copied,
        dict(compiled.params),
        columns,
        projected,
    )


def bounded(query: ReadQuery, limit: int = 50) -> ReadQuery:
    if not 1 <= limit <= 100:
        raise ValueError("Invalid inspection limit")
    statement = query.statement
    if isinstance(statement, Select):
        subquery = statement.subquery("provenance_rows")
        bounded_statement: Executable = select(*subquery.c).limit(limit)
    elif isinstance(statement, TextClause):
        bounded_statement = text(
            "SELECT * FROM (" + statement.text + ") AS provenance_rows LIMIT :provenance_row_limit"
        ).bindparams(*statement._bindparams.values(), bindparam("provenance_row_limit", limit))
    else:
        raise ValueError("Unsupported registered statement")
    return ReadQuery(bounded_statement, query.parameters)


def projection_columns(sql: str) -> tuple[str, ...]:
    """Metadata for simple, fixed repository projections; complex stars need a declared schema."""
    # SQL is application-owned. This deliberately rejects unresolved projections.
    tokens = re.finditer(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|[()]|\bSELECT\b|\bFROM\b|,", sql, re.I
    )
    depth = 0
    start = None
    columns = []
    for token in tokens:
        value = token.group().upper()
        if value == "(":
            depth += 1
        elif value == ")":
            depth -= 1
        elif depth == 0 and value == "SELECT":
            start = token.end()
        elif depth == 0 and start is not None and value in {",", "FROM"}:
            expression = sql[start : token.start()].strip()
            expression = re.sub(r"^DISTINCT\s+", "", expression, flags=re.I)
            match = re.search(r"\s+(?:AS\s+)?([a-z_][a-z_0-9]*)$", expression, re.I)
            name = match.group(1) if match else expression.split("::")[0].split(".")[-1]
            if re.fullmatch(r"(?:[a-z_]+\.)?\*", expression, re.I) or not re.fullmatch(
                r"[a-z_][a-z_0-9]*", name, re.I
            ):
                raise ValueError("Projection requires explicit registered columns")
            columns.append(name)
            start = token.end()
            if value == "FROM":
                break
    if not columns:
        raise ValueError("Projection requires explicit registered columns")
    return tuple(columns)
