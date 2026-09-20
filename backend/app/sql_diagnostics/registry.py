"""Only code-owned SELECTs. No client-controlled SQL, tables, columns or parameters."""

from dataclasses import replace
from types import MappingProxyType
from uuid import UUID

from app.errors import APIError
from app.repositories.quality_sources import POINT_MISSING_SQL
from app.repositories.queues import QUEUE_SQL
from app.sql_diagnostics.models import SqlDiagnosticRecipe, StoredFinding

MAX_ROWS = 50
HARD_MAX_ROWS = 100
SENSITIVE_FIELDS = frozenset(
    {
        "password_hash",
        "api_import_token",
        "activate_token",
        "accept_token",
        "password_reset_token",
        "session_token",
        "smtp_password",
        "database_url",
    }
)
DATE_SQL = """SELECT uuid, event_uuid, start_date, start_time, end_date, end_time,
all_day, release_status::text
FROM uranus.event_date WHERE uuid = :entity_key"""
DATE_FIELDS = (
    "uuid",
    "event_uuid",
    "start_date",
    "start_time",
    "end_date",
    "end_time",
    "all_day",
    "release_status",
)


def recipe(
    rule: str,
    title: str,
    kind: str,
    fields: tuple[str, ...],
    sql: str,
    columns: tuple[str, ...],
    explanation: str,
) -> SqlDiagnosticRecipe:
    if SENSITIVE_FIELDS.intersection(columns) or not sql.startswith("SELECT ") or ";" in sql:
        raise ValueError("Unsafe diagnostic recipe")
    return SqlDiagnosticRecipe(
        rule, rule, title, sql + "\nLIMIT :diagnostic_limit", columns, kind, fields, explanation
    )


RECIPES = (
    recipe(
        "event_date_end_before_start",
        "Enddatum liegt vor Startdatum",
        "event_date",
        ("end_date",),
        DATE_SQL,
        DATE_FIELDS,
        "Enddatum vorhanden und Enddatum < Startdatum.",
    ),
    recipe(
        "event_date_same_day_end_before_start",
        "Endzeit liegt vor Startzeit",
        "event_date",
        ("end_time",),
        DATE_SQL,
        DATE_FIELDS,
        "Gleiches Start- und Enddatum; beide Zeiten vorhanden; Endzeit < Startzeit.",
    ),
    recipe(
        "event_date_without_location",
        "Termin ohne wirksamen Ort",
        "event_date",
        ("venue_uuid",),
        """SELECT d.uuid, d.event_uuid, d.venue_uuid AS date_venue_uuid,
d.space_uuid AS date_space_uuid, e.venue_uuid AS event_venue_uuid,
e.space_uuid AS event_space_uuid, e.online_link
FROM uranus.event_date d LEFT JOIN uranus.event e ON e.uuid = d.event_uuid
WHERE d.uuid = :entity_key""",
        (
            "uuid",
            "event_uuid",
            "date_venue_uuid",
            "date_space_uuid",
            "event_venue_uuid",
            "event_space_uuid",
            "online_link",
        ),
        "Python: wirksames Venue fehlt und valid_online(online_link) ist falsch. "
        "Die bestehende Ortsvererbung gilt.",
    ),
    recipe(
        "event_price_without_currency",
        "Preis ohne Währung",
        "event",
        ("currency",),
        """SELECT uuid, title, release_status::text, min_price, max_price,
currency, price_type::text
FROM uranus.event WHERE uuid = :entity_key""",
        ("uuid", "title", "release_status", "min_price", "max_price", "currency", "price_type"),
        "Mindestens ein Preis ist gesetzt und blank(currency) ist wahr "
        "(NULL, leer oder nur Whitespace).",
    ),
    recipe(
        "venue_missing_location",
        "Veranstaltungsort ohne Geoposition",
        "venue",
        ("point",),
        f"""SELECT uuid, name, org_uuid, street, house_number, postal_code, city, country,
state, osm_id, ST_AsText(point) AS point, {POINT_MISSING_SQL} AS point_missing
FROM uranus.venue WHERE uuid = :entity_key""",
        (
            "uuid",
            "name",
            "org_uuid",
            "street",
            "house_number",
            "postal_code",
            "city",
            "country",
            "state",
            "osm_id",
            "point",
            "point_missing",
        ),
        "point IS NULL OR ST_IsEmpty(point), wie in der Qualitätsprojektion.",
    ),
    recipe(
        "membership_joined_accept_token_present",
        "Beigetretene Mitgliedschaft mit Annahmetoken",
        "team_membership",
        ("accept_token",),
        """SELECT m.org_uuid, o.name AS organization_name, m.user_uuid, m.has_joined,
(m.accept_token IS NOT NULL AND btrim(m.accept_token) <> '') AS accept_token_present
FROM uranus.organization_member_link m
LEFT JOIN uranus.organization o ON o.uuid = m.org_uuid
WHERE m.org_uuid = :org_uuid AND m.user_uuid = :user_uuid""",
        ("org_uuid", "organization_name", "user_uuid", "has_joined", "accept_token_present"),
        "has_joined und accept_token_present sind wahr. Tokenwerte werden niemals ausgewählt.",
    ),
    recipe(
        "partner_long_pending",
        "Lange offene Partneranfrage",
        "partner_request",
        ("status",),
        """SELECT from_org_uuid, from_name AS from_org_name, to_org_uuid, to_name AS to_org_name,
user_id, user_exists, status, created_at, grant_exists
FROM ("""
        + QUEUE_SQL["partner_requests"]
        + """) partner
WHERE from_org_uuid = :from_org_uuid AND to_org_uuid = :to_org_uuid""",
        (
            "from_org_uuid",
            "from_org_name",
            "to_org_uuid",
            "to_org_name",
            "user_id",
            "user_exists",
            "status",
            "created_at",
            "grant_exists",
        ),
        "Python: status = pending und created_at älter als PENDING_AGE_DAYS; "
        "URANUS_TIMESTAMP_TIMEZONE interpretiert die Quellzeit.",
    ),
)
# One rule entry, with fixed variants for the polymorphic URL rule.
URL_QUERIES = MappingProxyType(
    {
        "event": (
            "SELECT uuid, title, source_link, online_link, ticket_link, registration_link "
            "FROM uranus.event WHERE uuid = :entity_key",
            ("uuid", "title", "source_link", "online_link", "ticket_link", "registration_link"),
            ("source_link", "online_link", "ticket_link", "registration_link"),
        ),
        "venue": (
            "SELECT uuid, name, web_link, ticket_link FROM uranus.venue WHERE uuid = :entity_key",
            ("uuid", "name", "web_link", "ticket_link"),
            ("web_link", "ticket_link"),
        ),
        "organization": (
            "SELECT uuid, name, web_link FROM uranus.organization WHERE uuid = :entity_key",
            ("uuid", "name", "web_link"),
            ("web_link",),
        ),
    }
)
URL_RECIPES = MappingProxyType(
    {
        kind: recipe(
            "url_syntax",
            "URL-Syntax",
            kind,
            fields,
            sql,
            columns,
            "Python: url_problem() prüft das gespeicherte Finding-Feld. "
            "Keine DNS- oder HTTP-Anfrage. "
            "Zugangsdaten und sensible URL-Parameter werden verdeckt.",
        )
        for kind, (sql, columns, fields) in URL_QUERIES.items()
    }
)
URL_RECIPES = MappingProxyType(
    {kind: replace(item, id=f"url_syntax.{kind}") for kind, item in URL_RECIPES.items()}
)
REGISTRY = MappingProxyType({item.rule: item for item in RECIPES})
PILOT_RULES = frozenset((*REGISTRY, "url_syntax"))
assert len(REGISTRY) == len(RECIPES)
assert len({item.id for item in RECIPES}) == len(RECIPES)


def resolve(finding: StoredFinding) -> SqlDiagnosticRecipe:
    item = (
        URL_RECIPES.get(finding.entity_type)
        if finding.rule == "url_syntax"
        else REGISTRY.get(finding.rule)
    )
    if item is None:
        raise APIError(404, "diagnostic_unavailable", "No SQL diagnostic available.")
    if finding.entity_type != item.entity_type or finding.field not in item.fields:
        raise APIError(
            422, "diagnostic_invalid_finding", "Finding is incompatible with this diagnostic."
        )
    return item


def parameters_for(finding: StoredFinding) -> dict[str, UUID | int]:
    resolve(finding)
    try:
        if finding.entity_type in {"team_membership", "partner_request"}:
            prefix, left, right = finding.entity_key.split(":")
            expected, names = (
                ("membership", ("org_uuid", "user_uuid"))
                if finding.entity_type == "team_membership"
                else ("partner-request", ("from_org_uuid", "to_org_uuid"))
            )
            if prefix != expected:
                raise ValueError
            result: dict[str, UUID | int] = dict(zip(names, (UUID(left), UUID(right)), strict=True))
        else:
            result = {"entity_key": UUID(finding.entity_key)}
    except (ValueError, AttributeError):
        raise APIError(422, "diagnostic_invalid_finding", "Invalid finding identity.") from None
    result["diagnostic_limit"] = min(MAX_ROWS, HARD_MAX_ROWS)
    return result
