"""Generate admin-only database documentation without connecting to a database."""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateSchema, CreateTable
from sqlalchemy.sql.ddl import sort_tables_and_constraints

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DUMMY_URL = "postgresql+asyncpg://dummy:dummy@localhost/dummy"
DIAGRAM_GROUPS: dict[str, tuple[str, ...]] = {
    "auth": (
        "auth_account",
        "auth_session",
        "auth_system_admin",
        "auth_journalist",
        "auth_login_bucket",
    ),
    "quality": (
        "check_run",
        "finding",
        "finding_event",
        "record_mark",
        "record_mark_event",
        "url_check",
    ),
    "workflow": ("assignment", "assignment_event", "finding", "auth_account"),
    "notifications": ("notification", "notification_delivery", "notification_delivery_item"),
    "geocoding": ("geo_area", "geocode_request", "geocode_candidate"),
}


class DocumentationError(Exception):
    """An actionable documentation generation failure."""


def validate_metadata(
    metadata: sa.MetaData, groups: Mapping[str, Sequence[str]]
) -> dict[str, sa.Table]:
    tables = {
        table.name: table
        for table in sorted(metadata.tables.values(), key=lambda table: table.fullname)
        if table.schema == "admin"
    }
    if not tables:
        raise DocumentationError("Metadata contains no admin tables.")
    for table in tables.values():
        for fk in sorted(table.foreign_keys, key=lambda fk: (fk.parent.name, fk.target_fullname)):
            try:
                target = fk.column
            except sa.exc.NoReferenceError as exc:
                raise DocumentationError(
                    f"Unresolved foreign key: {table.fullname}.{fk.parent.name} "
                    f"-> {fk.target_fullname}"
                ) from exc
            if target.table.schema != "admin":
                raise DocumentationError(
                    f"Foreign key outside admin: {table.fullname}.{fk.parent.name} "
                    f"-> {fk.target_fullname}"
                )
    for name, members in groups.items():
        missing = sorted(set(members) - tables.keys())
        if missing or not members:
            raise DocumentationError(f"Invalid diagram group {name}: missing tables {missing}.")
    return tables


def subprocess_environment() -> dict[str, str]:
    # Do not pass credentials, application settings or dotenv configuration to tools.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR") if key in os.environ}
    env.update(
        ADMIN_MIGRATION_DATABASE_URL=DUMMY_URL,
        PYTHONHASHSEED="0",
        PYTHONUTF8="1",
        SOURCE_DATE_EPOCH="0",
        TZ="UTC",
        LANG="C.UTF-8",
    )
    return env


def run_tool(command: Sequence[str]) -> str:
    print(f"Running: {' '.join(command)}", flush=True)
    result = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        env=subprocess_environment(),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.returncode:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        raise DocumentationError(f"{Path(command[0]).name} failed (exit {result.returncode}).")
    return result.stdout


def alembic_command(*arguments: str) -> list[str]:
    return [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), *arguments]


def validate_head() -> str:
    output = run_tool(alembic_command("heads"))
    print(output, end="" if output.endswith("\n") else "\n")
    heads = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_heads()
    if len(heads) != 1:
        raise DocumentationError(f"Expected exactly one Alembic head, found {len(heads)}: {heads}")
    return heads[0]


def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def foreign_keys(table: sa.Table) -> list[sa.ForeignKeyConstraint]:
    return sorted(
        table.foreign_key_constraints,
        key=lambda constraint: (
            tuple(
                (fk.parent.name, fk.column.table.fullname, fk.column.name)
                for fk in constraint.elements
            ),
            str(constraint.name or ""),
        ),
    )


def pg_dialect() -> PGDialect:
    # SQLAlchemy does not annotate this dialect constructor.
    return PGDialect()  # type: ignore[no-untyped-call]


def render_schema_sql(metadata: sa.MetaData) -> str:
    tables = validate_metadata(metadata, {})
    dialect = pg_dialect()
    statements = [
        "-- Final admin schema from app.admin_tables.metadata; not migration history.\n"
        "-- Documentation only: no roles/grants or Alembic version table.\n"
        "-- PostGIS is a prerequisite.",
        str(CreateSchema("admin").compile(dialect=dialect)) + ";",
    ]
    deferred: set[sa.ForeignKeyConstraint] = set()
    # SQLAlchemy's public dependency sorter is not typed.
    ordered = sort_tables_and_constraints(list(tables.values()))  # type: ignore[no-untyped-call]
    for table, inline in ordered:
        if table is None:
            deferred.update(inline)
        else:
            statements.append(
                str(
                    CreateTable(table, include_foreign_key_constraints=inline).compile(
                        dialect=dialect
                    )
                ).strip()
                + ";"
            )
    # Only actual dependency cycles/use_alter require separate FK statements.
    # Self references remain inline; never mutate application metadata while compiling.
    for table in tables.values():
        for constraint in foreign_keys(table):
            if constraint in deferred:
                statements.append(
                    str(
                        AddConstraint(constraint, isolate_from_table=False).compile(dialect=dialect)
                    ).strip()
                    + ";"
                )
    for table in tables.values():
        statements.extend(
            sorted(
                str(CreateIndex(index).compile(dialect=dialect)).strip() + ";"
                for index in table.indexes
            )
        )
    return "\n\n".join(statements) + "\n"


def dbml_identifier(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value) else quote(value)


def dbml_type(type_: sa.types.TypeEngine[Any]) -> str:
    from app.geo_types import Geometry

    if isinstance(type_, Geometry):
        return f"geometry({type_.shape},{type_.srid})"
    if isinstance(type_, sa.DateTime):
        return "timestamptz" if type_.timezone else "timestamp"
    # More specific subclasses must precede their base types.
    for class_, name in (
        (sa.Uuid, "uuid"),
        (sa.Text, "text"),
        (sa.BigInteger, "bigint"),
        (sa.SmallInteger, "smallint"),
        (sa.Integer, "integer"),
        (sa.Boolean, "boolean"),
        (postgresql.JSONB, "jsonb"),
        (sa.Double, "double"),
    ):
        if isinstance(type_, class_):
            return name
    compiled = type_.compile(dialect=pg_dialect()).lower()
    return quote(compiled) if re.search(r"\s", compiled) else compiled


def dbml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def dbml_expression(value: str) -> str:
    return "`" + value.replace("\\", "\\\\").replace("`", "\\`") + "`"


def dbml_default(column: sa.Column[Any]) -> str | None:
    dialect = pg_dialect()
    default = column.server_default
    if not isinstance(default, sa.DefaultClause):
        return None
    expression = sa.literal(default.arg) if isinstance(default.arg, str) else default.arg
    value = str(expression.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    if value.lower() in {"true", "false", "null"}:
        return value.lower()
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", value):
        return value
    if value.startswith("'") and value.endswith("'"):
        literal = value[1:-1].replace("''", "'")
        if isinstance(column.type, (sa.Integer, sa.Numeric, sa.Float)) and re.fullmatch(
            r"[-+]?\d+(\.\d+)?", literal
        ):
            return literal
        return dbml_string(literal)
    return dbml_expression(value)


def dbml_columns(names: Sequence[str]) -> str:
    identifiers = [dbml_identifier(name) for name in names]
    return identifiers[0] if len(names) == 1 else f"({', '.join(identifiers)})"


def render_dbml(metadata: sa.MetaData) -> str:
    tables = validate_metadata(metadata, {})
    lines = [
        "// Final admin schema for dbdiagram.io; generated from SQLAlchemy metadata.",
        "// CHECK constraints are in admin-schema.sql; PostgreSQL-only indexes appear as Notes.",
        "Project uranus_admin {",
        "  database_type: 'PostgreSQL'",
        "}",
        "",
    ]
    dialect = pg_dialect()
    for table in tables.values():
        lines.append(f"Table admin.{dbml_identifier(table.name)} {{")
        pk = [column.name for column in table.primary_key.columns]
        unique = sorted(
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        )
        for column in table.columns:
            settings = ["pk"] if pk == [column.name] else []
            if not column.nullable:
                settings.append("not null")
            if (column.name,) in unique:
                settings.append("unique")
            default = dbml_default(column)
            if default is not None:
                settings.append(f"default: {default}")
            suffix = f" [{', '.join(settings)}]" if settings else ""
            lines.append(f"  {dbml_identifier(column.name)} {dbml_type(column.type)}{suffix}")
        indexes = [f"{dbml_columns(pk)} [pk]"] if len(pk) > 1 else []
        indexes.extend(f"{dbml_columns(cols)} [unique]" for cols in unique if len(cols) > 1)
        notes = []
        for index in sorted(table.indexes, key=lambda index: str(index.name)):
            options = index.dialect_options["postgresql"]
            method = options.get("using") or "btree"
            if options.get("where") is not None or method not in {"btree", "hash"}:
                # Do not misrepresent partial uniqueness as unconditional uniqueness.
                notes.append(str(CreateIndex(index).compile(dialect=dialect)))
                continue
            expressions = [
                dbml_identifier(expr)
                if isinstance(expr, str)
                else dbml_identifier(expr.name)
                if isinstance(expr, sa.Column)
                else dbml_expression(
                    str(
                        expr.compile(
                            dialect=dialect,
                            compile_kwargs={"literal_binds": True, "include_table": False},
                        )
                    )
                )
                for expr in index.expressions
            ]
            settings = [f"name: {dbml_string(str(index.name))}", f"type: {method}"]
            if index.unique:
                settings.append("unique")
            columns = expressions[0] if len(expressions) == 1 else f"({', '.join(expressions)})"
            indexes.append(f"{columns} [{', '.join(settings)}]")
        if indexes:
            lines.extend(["", "  indexes {", *(f"    {index}" for index in indexes), "  }"])
        if notes:
            lines.append(f"  Note: {dbml_string('PostgreSQL indexes: ' + '; '.join(notes))}")
        lines.extend(["}", ""])
    for table in tables.values():
        for number, constraint in enumerate(foreign_keys(table), 1):
            source = dbml_columns([fk.parent.name for fk in constraint.elements])
            target = dbml_columns([fk.column.name for fk in constraint.elements])
            target_table = dbml_identifier(constraint.referred_table.name)
            name = dbml_identifier(f"{table.name}_fk_{number}")
            actions = [
                f"{key}: {action.lower()}"
                for key, action in (
                    ("delete", constraint.ondelete),
                    ("update", constraint.onupdate),
                )
                if action
            ]
            suffix = f" [{', '.join(actions)}]" if actions else ""
            lines.append(
                f"Ref {name}: admin.{dbml_identifier(table.name)}.{source} "
                f"> admin.{target_table}.{target}{suffix}"
            )
    return "\n".join(lines) + "\n"


def render_dot(tables: Mapping[str, sa.Table], selected: Sequence[str], title: str) -> str:
    """Render declared constraints only; never infer relations from column names."""
    names = sorted(selected)
    nodes = {name: f"t{index}" for index, name in enumerate(names)}
    ports = {
        (name, column.name): f"c{index}"
        for name in names
        for index, column in enumerate(tables[name].columns)
    }
    legend = (
        f"Admin schema | {title}\n"
        "PK1, PK2 = ordered parts of one primary key; FK = foreign key; U1, U2 = unique groups\n"
        "Arrows: referencing column -> referenced column; F1.1, F1.2 = parts of one foreign key\n"
        "Unique indexes and CHECK constraints: see admin-schema.sql"
    )
    lines = [
        "digraph admin {",
        "  graph [rankdir=LR, ranksep=1.3, nodesep=0.6, pad=0.3, splines=spline,",
        '         pack=true, packmode="array3",',
        f'         fontname="DejaVu Sans", fontsize=12, labelloc=t, label={quote(legend)}];',
        '  node [shape=plain, fontname="DejaVu Sans", fontsize=11];',
        '  edge [fontname="DejaVu Sans", fontsize=10, color="#475569", arrowsize=0.8];',
    ]
    dialect = pg_dialect()
    for name in names:
        table = tables[name]
        pk = {column.name: index for index, column in enumerate(table.primary_key.columns, 1)}
        unique = sorted(
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        )
        lines.extend(
            [
                f"  {nodes[name]} [label=<",
                '    <TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
                'CELLPADDING="5" COLOR="#64748b">',
                '      <TR><TD COLSPAN="4" BGCOLOR="#e2e8f0">'
                f'<FONT POINT-SIZE="14"><B>{html.escape(table.fullname)}</B></FONT></TD></TR>',
                "      <TR><TD><B>Key</B></TD><TD><B>Column</B></TD>"
                "<TD><B>PostgreSQL type</B></TD><TD><B>Nullability</B></TD></TR>",
            ]
        )
        for column in table.columns:
            tags = [f"PK{pk[column.name]}"] if column.name in pk else []
            if column.foreign_keys:
                tags.append("FK")
            tags.extend(f"U{index}" for index, cols in enumerate(unique, 1) if column.name in cols)
            color = "#eff6ff" if column.primary_key else "#ffffff"
            lines.append(
                f'      <TR><TD PORT="{ports[name, column.name]}_in" '
                f'BGCOLOR="{color}">{", ".join(tags)}</TD>'
                '<TD ALIGN="LEFT">'
                f"{html.escape(column.name)}</TD>"
                f'<TD ALIGN="LEFT">{html.escape(column.type.compile(dialect=dialect))}</TD>'
                f'<TD ALIGN="LEFT" PORT="{ports[name, column.name]}_out">'
                f"{'NULL' if column.nullable else 'NOT NULL'}</TD></TR>"
            )
        lines.extend(["    </TABLE>", "  >];"])
    for name in names:
        for number, constraint in enumerate(foreign_keys(tables[name]), 1):
            for part, fk in enumerate(constraint.elements, 1):
                target = fk.column
                if target.table.name not in nodes:
                    continue
                source_port = ports[name, fk.parent.name]
                target_port = ports[target.table.name, target.name]
                source_endpoint = (
                    f"{source_port}_in:w"
                    if target.table is tables[name]
                    else f"{source_port}_out:e"
                )
                tooltip = f"{name}.{fk.parent.name} -> {target.table.fullname}.{target.name}"
                lines.append(
                    f"  {nodes[name]}:{source_endpoint} -> "
                    f"{nodes[target.table.name]}:{target_port}_in:w "
                    f'[label="F{number}.{part}", '
                    f"tooltip={quote(tooltip)}];"
                )
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate(
    output_dir: Path,
    *,
    only: str | None = None,
    skip_migrations: bool = False,
    skip_schema_sql: bool = False,
    skip_dbml: bool = False,
    skip_pdf: bool = False,
) -> None:
    from app.admin_tables import metadata

    dot = shutil.which("dot")
    if dot is None:
        raise DocumentationError(
            "Graphviz 'dot' not found. Install it with: sudo apt install graphviz"
        )
    tables = validate_metadata(metadata, DIAGRAM_GROUPS)
    head = validate_head()
    groups = {"full": tuple(tables), **DIAGRAM_GROUPS}
    chosen = [only] if only else list(groups)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Publish only after all requested files have been generated successfully.
    with tempfile.TemporaryDirectory(prefix=".database-docs-", dir=output_dir) as temporary:
        staging = Path(temporary)
        if not skip_migrations:
            sql = run_tool(alembic_command("upgrade", "head", "--sql"))
            if not sql.strip():
                raise DocumentationError("Alembic produced empty SQL.")
            (staging / "admin-migrations.sql").write_text(sql, encoding="utf-8")
        if not skip_schema_sql:
            (staging / "admin-schema.sql").write_text(render_schema_sql(metadata), encoding="utf-8")
        if not skip_dbml:
            (staging / "admin-schema.dbml").write_text(render_dbml(metadata), encoding="utf-8")
        for group in chosen:
            path = staging / f"admin-er-{group}.dot"
            path.write_text(render_dot(tables, groups[group], group.upper()), encoding="utf-8")
            for format_ in ["svg"] if skip_pdf else ["svg", "pdf"]:
                target = path.with_suffix(f".{format_}")
                output = run_tool([dot, f"-T{format_}", str(path), "-o", str(target)])
                if output:
                    print(output, end="" if output.endswith("\n") else "\n")
                if not target.is_file() or not target.stat().st_size:
                    raise DocumentationError(f"Graphviz produced no content for {target.name}.")
        for path in sorted(staging.iterdir()):
            target = output_dir / path.name
            path.replace(target)
            print(f"Wrote {target} ({target.stat().st_size} bytes)")
    print(f"Documented {len(tables)} admin tables; Alembic head: {head}.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_ROOT / "docs" / "database",
        help="Output directory (relative paths use the current working directory).",
    )
    parser.add_argument(
        "--skip-migrations",
        "--skip-ddl",
        dest="skip_migrations",
        action="store_true",
        help="Do not generate migration SQL (--skip-ddl is the legacy alias).",
    )
    parser.add_argument("--skip-schema-sql", action="store_true", help="Skip final schema SQL.")
    parser.add_argument("--skip-dbml", action="store_true", help="Skip final schema DBML.")
    parser.add_argument("--skip-pdf", action="store_true", help="Generate DOT/SVG without PDF.")
    parser.add_argument("--only", choices=["full", *DIAGRAM_GROUPS], help="Generate one diagram.")
    args = parser.parse_args(argv)
    try:
        generate(
            args.output_dir.resolve(),
            only=args.only,
            skip_migrations=args.skip_migrations,
            skip_schema_sql=args.skip_schema_sql,
            skip_dbml=args.skip_dbml,
            skip_pdf=args.skip_pdf,
        )
    except (DocumentationError, sa.exc.SQLAlchemyError, OSError) as exc:
        print(f"Database documentation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    # Support `python scripts/generate_database_docs.py` without installing the app.
    sys.path.insert(0, str(BACKEND_ROOT))
    raise SystemExit(main())
