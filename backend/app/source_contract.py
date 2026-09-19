"""Versioned minimum column/type contract for the deterministic quality snapshot.

Audited against Uranus main 15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e.
This is not a complete Uranus schema mirror or a runtime GitHub dependency.
accept_token is catalog metadata only; domain SQL projects a boolean.
"""

from collections.abc import Mapping, Sequence
from typing import Any

AUDITED_URANUS_SHA = "15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e"
QUALITY_SOURCE_CONTRACT: dict[str, dict[str, str]] = {
    "organization": {
        "uuid": "uuid",
        "name": "text",
        "street": "varchar",
        "house_number": "varchar",
        "address_addition": "varchar",
        "postal_code": "varchar",
        "city": "varchar",
        "country": "varchar",
        "state": "varchar",
        "point": "geometry",
        "web_link": "text",
        "contact_email": "varchar",
    },
    "venue": {
        "uuid": "uuid",
        "name": "varchar",
        "org_uuid": "uuid",
        "street": "varchar",
        "house_number": "varchar",
        "postal_code": "varchar",
        "city": "varchar",
        "country": "bpchar",
        "state": "varchar",
        "osm_id": "int8",
        "point": "geometry",
        "web_link": "text",
        "ticket_link": "text",
        "contact_email": "varchar",
    },
    "space": {
        "uuid": "uuid",
        "name": "text",
        "venue_uuid": "uuid",
        "web_link": "text",
        "total_capacity": "int4",
        "seating_capacity": "int4",
        "area_sqm": "numeric",
    },
    "event": {
        "uuid": "uuid",
        "title": "text",
        "org_uuid": "uuid",
        "venue_uuid": "uuid",
        "space_uuid": "uuid",
        "release_status": "event_release_status",
        "source_link": "text",
        "online_link": "text",
        "ticket_link": "text",
        "registration_link": "text",
        "registration_email": "text",
        "registration_phone": "text",
        "min_price": "float8",
        "max_price": "float8",
        "currency": "varchar",
        "price_type": "uranus_price_type",
        "description": "text",
        "categories": "_int4",
        "languages": "_text",
    },
    "event_date": {
        "uuid": "uuid",
        "event_uuid": "uuid",
        "venue_uuid": "uuid",
        "space_uuid": "uuid",
        "release_status": "event_release_status",
        "start_date": "date",
        "start_time": "time",
        "end_date": "date",
        "end_time": "time",
        "all_day": "bool",
        "ticket_link": "text",
    },
    "event_link": {
        "id": "int4",
        "event_uuid": "uuid",
        "type": "text",
        "url": "text",
    },
    "event_type_link": {"event_uuid": "uuid", "type_id": "int4", "genre_id": "int4"},
    "event_category": {"category_id": "int4"},
    "event_type": {"type_id": "int4"},
    "genre_type": {"genre_id": "int4"},
    "language": {"code_iso_639_1": "varchar"},
    "link_type": {"key": "text"},
    "organization_member_link": {
        "org_uuid": "uuid",
        "user_uuid": "uuid",
        "has_joined": "bool",
        "accept_token": "text",
    },
    "license": {"key": "text", "url": "text"},
    "pluto_image": {"uuid": "uuid", "created_at": "timestamp", "mime_type": "text"},
    "pluto_image_link": {
        "context": "text",
        "context_uuid": "uuid",
        "identifier": "text",
        "pluto_image_uuid": "uuid",
    },
}


def compare_contract(columns: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    actual = {(row["table_name"], row["column_name"]): row for row in columns}
    tables = {table for table, _ in actual}
    missing_tables = sorted(set(QUALITY_SOURCE_CONTRACT) - tables)
    missing_columns = []
    type_mismatches = []
    for table, fields in QUALITY_SOURCE_CONTRACT.items():
        for column, expected in fields.items():
            row = actual.get((table, column))
            if row is None:
                if table not in missing_tables:
                    missing_columns.append(
                        {
                            "table": table,
                            "column": column,
                            "category": "missing_required_source_column",
                        }
                    )
            elif row["udt_name"] != expected or (
                expected == "geometry"
                and row.get("formatted_type", "").lower() != "geometry(point,4326)"
            ):
                type_mismatches.append(
                    {
                        "table": table,
                        "column": column,
                        "category": "source_type_mismatch",
                        "expected": "geometry(Point,4326)" if expected == "geometry" else expected,
                    }
                )
    compatible = not (missing_tables or missing_columns or type_mismatches)
    return {
        "diagnostic": "source_schema_drift",
        "capability": "quality_snapshot",
        "compatible": compatible,
        "audited_uranus_sha": AUDITED_URANUS_SHA,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "type_mismatches": type_mismatches,
    }
