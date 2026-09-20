import json
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from pydantic import BaseModel

from app.config import Settings
from app.errors import APIError
from app.sql_diagnostics.provenance.models import (
    ProvenanceDefinition,
    ProvenanceResult,
    ProvenanceSource,
)
from app.sql_diagnostics.provenance.registry import COVERAGE, build
from app.sql_diagnostics.provenance.render import bounded, parameter_json
from app.sql_diagnostics.readonly import read_registered_rows
from app.sql_diagnostics.render import json_value

POST_PROCESSING = {
    "dashboard": [
        (
            "period_window() bestimmt [Start, Ende) mit ADMIN_TIMEZONE; Quellzeiten "
            "werden mit URANUS_TIMESTAMP_TIMEZONE interpretiert."
        ),
        (
            "persisted_counts(): resolved wird ausgeschlossen. Dringend: Priorität "
            "1/2 oder published_soon aus gespeicherten Metadaten."
        ),
        (
            "Die Arbeitslisten-Vorschau ist eine separate Findings-Abfrage "
            "(active_only=true, vier Zeilen, gewählter Schweregrad)."
        ),
        (
            "Prüfstatus ist unabhängig vom Zeitraum. Python summiert die pro Regel "
            "gespeicherten Counts."
        ),
    ],
    "activity": [
        (
            "period_window(), Cursor-Dekodierung und unbekannte Zeitstempel; "
            "Activity-Previews werden anhand der Seitenidentitäten nachgeladen."
        ),
        "Python erstellt geprüfte Links, Vorschautexte und Actions.",
    ],
    "findings": [
        (
            "persisted: stored_finding() liest Prioritäten aus gespeicherten "
            "Metadaten; active_only schließt resolved aus."
        ),
        (
            "Cursor enthält Priorität/ID. Die Query zeigt die echte Keyset-Bedingung;"
            " im räumlichen Pfad erfolgt Cursor/Seitenbildung erst nach Membership."
        ),
        (
            "live: load_sources()/scan() lädt mehrere Snapshots; Python wertet Regeln"
            " aus, filtert, priorisiert und paginiert. Einzelne SQL-Ergebnisse sind "
            "keine Live-Findings."
        ),
    ],
    "graph": [
        (
            "Python führt eine Breitensuche bis depth aus: Wurzel → Nachbarschaft → "
            "weitere Knoten → nächste Frontier."
        ),
        (
            "MAX_NODES=100, MAX_EDGES=200; nicht auflösbare Kanten werden entfernt. "
            "SQL-Ausführung zeigt nur einen begrenzten Query-Schritt, keinen "
            "vollständigen Graphen."
        ),
        (
            "Vorschauen/öffentliche Links werden zum Schluss gebündelt geladen; D3 "
            "berechnet das Layout im Browser."
        ),
    ],
    "statistics": [
        (
            "statistics_window(), automatic_interval()/bucket_windows(): natürliche "
            "Zeitzonenintervalle einschließlich DST."
        ),
        (
            "Python gruppiert Aggregatzeilen in Zeitreihen, summiert Totals, ordnet "
            "Vergleichszeiträume zu und erzeugt Recent-Links."
        ),
    ],
    "statistics.content": [
        (
            "period_window()/previous_window(); Python berechnet Coverage-Prozente, "
            "Anteile und Ranking-Deltas aus den SQL-Aggregaten."
        )
    ],
}


def definition(view: str, params: BaseModel, settings: Settings) -> ProvenanceDefinition:
    now = getattr(params, "as_of", None) or datetime.now(UTC)
    entry = next(row for row in COVERAGE if row["view_id"] == view)
    sources = build(view, params, settings, now)
    output = []
    for source in sources:
        rendered = source.rendered
        description = source.description
        if rendered.projected:
            description += (
                " Sicherheitsprojektion: opaque JSON-/Snapshot-/Mailfelder der Runtime "
                "werden ausgelassen."
            )
        parameters = {key: parameter_json(value) for key, value in rendered.parameters.items()}
        if source.dependencies:
            # Empty planning arrays are not the actual runtime batch. Never present
            # their literals as the query that produced a real page.
            parameters = {
                key: "[erst aus vorherigem Query-Schritt bekannt]"
                if isinstance(value, (list, dict))
                or key in {"ids", "keys", "types", "geo_scope_wkb"}
                else value
                for key, value in parameters.items()
            }
        output.append(
            ProvenanceSource(
                id=source.id,
                title=source.title,
                datasource=source.datasource,
                description=description,
                sql=rendered.sql,
                copy_sql=None if source.dependencies else rendered.copy_sql,
                parameters=parameters,
                columns=list(rendered.columns),
                executable=not source.dependencies,
                implementation_ref=source.implementation_ref,
                dependencies=list(source.dependencies),
            )
        )
    query = params.model_dump(mode="json", exclude_none=True, exclude={"as_of", "id"})
    if view in {"dashboard", "quality"}:
        query.pop("severity", None)
    if query.get("cursor"):
        query.pop("page", None)
    endpoint = "/api/v1" + entry["endpoint"].replace("{id}", str(getattr(params, "id", "")))
    if query:
        endpoint += "?" + urlencode(query)
    post = [entry["post_processing"], *POST_PROCESSING.get(view, [])]
    if getattr(params, "geo_scope_id", None):
        post.append(
            "Geo-Scope: Admin lädt die gespeicherte EWKB-Grenze. Uranus-Membership "
            "verwendet autoritative Punkte; Findings werden in 500er-Batches räumlich"
            " geprüft, danach in Python gezählt/paginiert. Unaufgelöste abhängige "
            "Query-Schritte sind nicht ausführbar."
        )
    if view.startswith("queues."):
        post.append(
            "map_queue(): URANUS_TIMESTAMP_TIMEZONE, belegte "
            "Erstellungs-/Einladungszeit, timedelta.days, PENDING_AGE_DAYS / "
            "ACTIVATION_AGE_DAYS; keine erfundene Login-/Beitrittshistorie."
        )
    if view.startswith("geocoding"):
        post.append(
            "enrich(): Source-Fingerprint/point_missing bestimmt stale; Kandidaten "
            "nur bei aktueller Generation. Nominatim ist eine externe Worker-Quelle, "
            "keine SQL-Query und wird hier nicht aufgerufen."
        )
    return ProvenanceDefinition(
        view_id=view,
        title="SQL / Datenherkunft",
        endpoint=endpoint,
        sources=output,
        post_processing=post,
        notes=[
            (
                "Diese Ansicht besteht aus mehreren Abfragen und zusätzlicher "
                "Anwendungslogik. Definitionen führen keine View-SQL aus."
            ),
            (
                "Ausführung: maximal 50 Ergebniszeilen je Query. LIMIT/OFFSET der View "
                "bleiben innen erhalten; die Inspektion ergänzt eine äußere Begrenzung."
            ),
            (
                "Abhängige Schritte zeigen ihre Runtime-Definition; noch unbekannte "
                "Ergebnisparameter werden nicht erfunden. Copy/Ausführung ist dort "
                "deaktiviert."
            ),
            (
                "Admin-Provenance nutzt die Runtime-Rolle mit Schreibrechten. READ ONLY "
                "ist deshalb eine wichtige zusätzliche Sicherheitsgrenze; keine neue "
                "Rolle/Grants."
            ),
            (
                "as_of bindet die Zeitfensterberechnung. Ausführungen lesen jeweils einen"
                " neuen Snapshot, nicht den historischen Seiten-Snapshot."
            ),
        ],
        observed_at=now,
        parameters=params.model_dump(mode="json", exclude_none=True) | {"as_of": now.isoformat()},
    )


def result_value(value: Any, key: str) -> Any:
    # No opaque JSON maps: their nested field names are not a safe projection.
    if isinstance(value, dict):
        return "[strukturierter Inhalt ausgeblendet]"
    if isinstance(value, bytes):
        return "[Geometrie-Binärdaten ausgeblendet]"
    if isinstance(value, (list, tuple)):
        if len(value) > 100:
            return "[Array überschreitet Inspektionsgrenze]"
        return json.dumps([json_value(item) for item in value], ensure_ascii=False)
    return json_value(value, url=key.endswith(("_link", "_url")) or key == "url")


async def execute(
    request: Request, view: str, source_id: str, params: BaseModel, settings: Settings, actor: str
) -> ProvenanceResult:
    started = perf_counter()
    count = 0
    category = "diagnostic_failed"
    datasource = "unknown"
    safe_source = "unavailable"
    try:
        now = getattr(params, "as_of", None) or datetime.now(UTC)
        source = next(
            (item for item in build(view, params, settings, now) if item.id == source_id), None
        )
        if source is None:
            raise APIError(404, "diagnostic_unavailable", "Unknown registered source.")
        safe_source = source.id
        datasource = source.datasource
        if source.dependencies:
            raise APIError(
                409, "provenance_dependency", "Runtime-dependent query parameters are unavailable."
            )
        engine = (
            request.app.state.engine if datasource == "uranus" else request.app.state.admin_engine
        )
        if engine is None:
            raise APIError(503, "admin_storage_unconfigured", "Admin storage unavailable.")
        rows, observed = await read_registered_rows(
            engine, bounded(source.rendered.query), admin_boundary=datasource == "admin"
        )
        columns = source.rendered.columns
        if any(set(row) != set(columns) for row in rows):
            raise ValueError("Unexpected registered projection")
        safe = [{key: result_value(row[key], key) for key in columns} for row in rows]
        if len(json.dumps(safe).encode()) > 256 * 1024:
            raise ValueError("Result size exceeded")
        count = len(safe)
        category = "success"
        return ProvenanceResult(
            source_id=source.id,
            datasource=source.datasource,
            columns=list(columns),
            rows=safe,
            row_count=count,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            observed_at=observed,
            truncated=count == 50,
        )
    except APIError:
        category = "unavailable"
        raise
    except Exception as exc:
        code = getattr(exc, "sqlstate", None) or getattr(
            getattr(exc, "orig", None), "sqlstate", None
        )
        timeout = isinstance(exc, TimeoutError) or code in {"57014", "55P03"}
        category = "diagnostic_timeout" if timeout else "diagnostic_failed"
        raise APIError(504 if timeout else 503, category, "Registered inspection failed.") from None
    finally:
        logging.getLogger("admin.sql_provenance").info(
            "sql_provenance",
            extra={
                "actor_subject": actor,
                "view_id": view,
                "source_id": safe_source,
                "datasource": datasource,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "row_count": count,
                "error_type": category,
            },
        )
