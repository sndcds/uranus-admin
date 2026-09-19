Aktueller ergänzender Audit: [Quality Rules v2](quality-rules.md) gegen Uranus main
`15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e`, einschließlich des lokalen
Source-Contract-Manifests. Die folgenden datierten Befunde bleiben historische Evidenz.

# Uranus-dev-Verifikation, 2026-09-14

Geprüfter aktueller Remote-Commit: **733c54133362460353400eb96c60a0cdb9f8450a**.
Abgerufen über GitHub; DDL und Handler wurden aus diesem Stand gelesen. Die ältere Analyse
unter [uranus-analysis.md](uranus-analysis.md) beruht auf 7feb47e und dem damals bereitgestellten
Backup. Diese Prüfung behauptet **keine neue Verbindung zum produktiven Live-Server**.
Die Integrationstests verwenden ausschließlich synthetische Daten auf lokalem PostgreSQL/PostGIS.

| Sachverhalt | Bestätigter Befund im aktuellen dev | Konsequenz |
| --- | --- | --- |
| Venue scope | [venue.ddl](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/ddl/venue.ddl): Default `standard`, CHECK nur `organization/shared`; auch im früheren Backup bestätigt | Domain-DDL nicht ändern, keine Vermutung über erlaubte neue Scopes; Uranus muss den Widerspruch korrigieren |
| Space Features | [space_feature_link.ddl](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/ddl/space_feature_link.ddl): integer space_id, zusammengesetzter PK mit key, kein FK zu space.uuid | Keine spekulative Zuordnungsregel |
| Partner FKs/Status | [organization_partner_request.ddl](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/ddl/organization_partner_request.ddl): keine Org-/User-FKs, Textstatus, UNIQUE(from,to) | Composite Key; fehlende Referenzen und unbekannte Status prüfen |
| Partner Richtung | [Annahmehandler](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/api/admin_insert_org_partner_request.go): pending → accepted; für A → B Grant B → A, permissions=0; Ablehnung löscht | Nur pending/accepted als belegte aktuelle Status, keine Entscheidungshistorie; fehlender Accepted-Grant ist Hinweis |
| Membership | [organization_member_link.ddl](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/ddl/organization_member_link.ddl): UNIQUE(org,user), echte FKs, invited_at nullable, has_joined | Keine Doppel-Membership-Regel gegen bereits erzwungenes Unique; invited_at statt created_at als Einladungsalter |
| Rechtepaare | [user_organization_link.ddl](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/ddl/user_organization_link.ddl): kein Unique-Paar; user_venue/user_space/user_event ebenfalls ohne Paar-Unique | Keine Hochstufung von Org-/Objektrechten zu globalem Admin; keine neue Rechte-/Nullrechte-Regel |
| Zeitfelder | DDL: überwiegend timestamp without time zone; pluto_image.created_at nullable, Bildlinks/Grants ohne Zeiten | Source-Zeitzone explizit; keine Login-, Beitritts-, Entscheidungs- oder Bildverwendungshistorie erfinden |
| Space-Vererbung | [öffentliche Projektion](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/sql/get-events-projected.sql) verwendet COALESCE für Space; [Terminabfrage](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/sql/get-event-dates.sql) verwendet bedingte Vererbung nach Venue-Override | Historischer Befund; aktuelle Regel verwendet `event_date_location_override` und unterdrückt Event-Space bei Termin-Venue-Override (siehe aktueller Audit unten) |
| Bildkontexte/Identifier | [api_image_helper.go](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/api/api_image_helper.go), [admin_pluto_image.go](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/api/admin_pluto_image.go): organization/venue/event/portal; Space auskommentiert; konkrete Identifier-Listen | Genau diese Listen prüfen; kein pauschales Space-Pflichtbild |
| Portal-Ziel | Portal-Handler verwenden Tabelle portal, DDL exportiert portal2/portal_temp; keine eindeutige aktuelle Zielauflösung | Portal-Identifier prüfen, Portal-Zielexistenz und Orgzuordnung aussetzen; kein Erraten einer Tabelle |
| Wikidata/Wikipedia | Kein einheitlicher URL-vs-Identifier-Vertrag durch die geprüften Quellen belegt | Beide Felder bewusst aus URL-Regel ausgeschlossen |

Die vorhandene read-only-Transaktion, SQL-Parameterbindung, Auth-Sperre ohne globale Berechtigung,
Migrationstrennung und Proxy-Allowlist erfüllten bereits wichtige Review-Anforderungen. Sie wurden
beibehalten; die Admin-Allowlist wurde lediglich um konkrete neue Operationen erweitert.

## Implementierte Regeln

Alle Regeln haben dasselbe Finding-/Prioritätsmodell; Regelversion dieser Einführung: 1.

| rule_code | Typische Severity / Grundlage |
| --- | --- |
| venue_missing_geolocation (bestehend) | warning; NULL/EMPTY point, effektive kommende Termine |
| url_syntax | warning; alle 11 benannten URL-Quellfelder, mit Feldkennung und konkretem Syntaxgrund |
| event_without_dates | error bei released/rescheduled, sonst warning |
| event_without_location | Terminloses Event ohne Venue und gültige Online-Alternative; Status bestimmt Severity |
| event_date_without_location | Je Termin effektives Venue; valide Online-Alternative, Status bestimmt Severity |
| event_date_space_venue_mismatch | error; expliziter/geerbter Space widerspricht effektivem Venue nach öffentlichem Vertrag |
| image_link_without_image | error; NULL oder nicht existentes Bild |
| image_link_unknown_context | warning; Kontext nicht im bestätigten Handlervertrag |
| image_link_invalid_identifier | warning; Identifier nicht für bestätigten Kontext erlaubt |
| image_link_missing_target | error; fehlendes Organization-/Venue-/Event-Ziel; Portal ausdrücklich nicht abgedeckt |
| image_orphaned_upload | info; keine Verknüpfung, bekannter created_at strikt älter als 48 Stunden (konfigurierbar) |
| partner_self_request | error |
| partner_missing_organization | error |
| partner_missing_user | error |
| partner_unknown_status | warning |
| partner_long_pending | warning; strikt älter als PENDING_AGE_DAYS |
| partner_accepted_without_grant | info; exakte B → A-Richtung, Rechtewert beliebig einschließlich 0 |
| team_invitation_old | warning; false has_joined und belegtes altes invited_at |
| user_activation_old | info; is_active=false, alte Neuanlage, keine Login-Aussage |

URL-Regel: organization.web_link; venue.web_link/ticket_link; space.web_link;
event.source_link/online_link/ticket_link/registration_link; event_date.ticket_link;
event_link.url; license.url. Das sind elf explizit benannte Felder. Optional leere Links sind
kein Syntaxfehler; Schema, Host, eingebettete Whitespaces und Parserfehler werden unterschieden.
Kein pauschales Voranstellen von https://, keine Netzwerkabfrage.

## Live schema verification (operator command)

Run deliberately against the authoritative read-only source connection:

```bash
cd backend
uv run python -m app.source_schema_verify --json > source-schema-report.json
```

The command uses `DATABASE_URL` with a repeatable-read, read-only transaction and
statement timeout. It reports columns/defaults/types, constraints (including foreign
keys/checks/unique pairs), indexes, bounded observed `venue.scope` and partner-request
status values, plus missing tables. It never selects account credentials or user rows.
Catalog visibility depends on the reader's grants; missing information is not proof
that a constraint does not exist. A configured timezone is reported, not inferred:
`timestamp without time zone` alone establishes no storage timezone.

Review scope/default/check consistency; the integer space-feature key versus space
identity; partner directions/FKs/status; membership and permission pair uniqueness;
and all timestamp types. Preserve the report with the deployment's verification date
and operator-confirmed storage timezone. Only then enable rules relying on newly
confirmed semantics.

**Status:** the command is tested against disposable schema fixtures. No live
production verification was performed for this change. Issue #13 remains open until
an operator runs it on the authoritative source and records the reviewed findings.

## Current audit: 2026-09-17 — repository evidence, no live access

Admin baseline: `7428b455f68316c2b116798ac1138d70eeeb3d2c`.
Uranus default branch is **main**, reviewed at
[`74fef734ca916ecd04aef9d7d3013c1cd918d6dc`](https://github.com/sndcds/uranus/tree/74fef734ca916ecd04aef9d7d3013c1cd918d6dc).
The dated dev review above is historical evidence. The current review used a source
archive from GitHub, **not a database connection**. No explicitly authorized live
connection or reviewed live report was supplied; no credential search was performed.

| Bereich | Repo-Befund (current main) | Live-Befund | Status | Konsequenz |
| --- | --- | --- | --- | --- |
| Venue scope | `ddl/venue.ddl`: text, default `standard`, CHECK `organization/shared` | Nicht verifiziert | Offen | Export-Widerspruch nicht als aktuellen Live-Fehler ausgeben; keine neue Scope-Regel |
| Space feature | `ddl/space_feature_link.ddl`: integer `space_id`, PK `(space_id,key)`; FK nur von `key` zu `space_feature.key`, keiner zu `space.uuid` | Nicht verifiziert | Offen | Keine integer→UUID-Zuordnung erraten |
| Partner request | `ddl/organization_partner_request.ddl`: text status/default pending; Unique `(from_org_uuid,to_org_uuid)`; keine Org-/User-FKs | Nicht verifiziert | Offen | Missing-reference-Regeln beibehalten, aber Live-Abgleich vor Abschluss erforderlich |
| Partner direction | `api/admin_insert_org_partner_request.go`: A→B acceptance erzeugt B→A grant; rejection löscht Request | Nicht verifiziert | Repo-Handler bestätigt | Accepted ohne passenden Grant bleibt Hinweis; keine Entscheidungshistorie |
| Membership | `ddl/organization_member_link.ddl`: Unique `(org_uuid,user_uuid)`, FKs; `invited_at` und `has_joined` | Nicht verifiziert | Offen | Keine redundante Duplicate-Regel; Einladung und Beitritt getrennt halten |
| Permission pairs | `user_organization_link`, `user_venue_link`, `user_space_link`, `user_event_link`: kein Paar-Unique im jeweiligen Export | Nicht verifiziert | Offen | Live-Constraints/Unique-Indizes einschließlich Bedingungen prüfen; keine globale Berechtigung ableiten |
| Timestamp types/storage | Export enthält naive timestamps. Die frühere Betreiberbestätigung in `uranus-analysis.md` gilt für den dort genannten Backup; Konfigurationsdefault ist UTC | Aktuelle Storage-Konvention nicht neu bestätigt | Offen / historische Betreiberquelle vorhanden | Aktuelle Deployment-Konfiguration und Betreiberbestätigung separat erfassen; Typ allein beweist keine Zeitzone |

### Operator-ready execution and evidence review

1. Obtain explicit authorization for the authoritative source, including scope and
   deployment identity. Use the existing **SELECT-only reader** via `DATABASE_URL`.
   Possessing a DSN, localhost forwarding or a database snapshot is not proof of live
   authorization or freshness. Do not supply migration/runtime credentials instead.
2. Have the operator confirm `URANUS_TIMESTAMP_TIMEZONE` against the actual writers
   and deployment documentation. Record confirmation date/source; do not infer it from
   the connection timezone or the PostgreSQL column type.
3. Run the existing command in an environment where the authorized connection is
   already provided securely. Do not put a DSN into shell history or the report name:

   ```bash
   cd backend
   umask 077
   report_dir=$(mktemp -d "${TMPDIR:-/tmp}/uranus-schema.XXXXXX")
   uv run python -m app.source_schema_verify --json > "$report_dir/report.json"
   # Continue only after exit code 0; validate JSON without printing its contents:
   python -m json.tool "$report_dir/report.json" > /dev/null
   ```

4. Check `transaction_read_only=true`, `missing_tables`, column visibility and both
   completeness flags on observed values: `truncated` means over 100 values;
   `values_truncated` means a displayed value exceeded 80 characters. Neither a
   partial catalog nor truncated observations can establish a complete allowed-value
   contract. Confirm missing constraints using an authorized catalog reviewer, not
   by granting more runtime privileges automatically.
5. Review the private report before sharing. Database names, defaults, constraint
   definitions/index expressions and unexpected status values can reveal internal
   details. Do not commit the raw JSON. Publish only the facts needed in the table
   above, with verification date, source provenance and operator confirmation.
6. Audit the affected rules against those facts, add a regression only for a proven
   discrepancy, and record unchanged rules too. Close #13 only when all seven
   acceptance criteria have evidence. A successful tool run alone is insufficient.

### Rule dependency audit (code only)

- No rule maps `space_feature_link.space_id` to `space.uuid`, validates the disputed
  venue scope enum, or invents membership duplicates despite a Unique constraint.
- `services/queues.py` and `repositories/queues.py` retain A→B request / B→A accepted-grant
  semantics. Pending requests and accepted partnerships are different relationships.
- Invitation age uses `invited_at` and membership state uses `has_joined`; user
  activation age uses creation, never modified-at as last login.
- Source timestamps are converted using the configured source timezone. Existing
  backup confirmation does not substitute for confirmation of the current live writer.
- Current effective-location logic is centralized in `quality/core.py` and the shared
  SQL location expressions: a date venue override suppresses inherited event space.
  The older COALESCE description above is historical, not the current rule contract.

No quality-rule behavior was changed based on this repository-only audit.

## Logo quality audit — 2026-09-17

Before implementation, `uranus-admin` remote `main` was fetched and checked at
`8439992` (the working tree had the same HEAD). The existing core-rule evaluator,
Finding/Action contract, priority model and check-run persistence are reused.

Uranus remote `main` was fetched and inspected at
[`6fcdb489637001e12c676a9f5a7222cfbf75d4e7`](https://github.com/sndcds/uranus/tree/6fcdb489637001e12c676a9f5a7222cfbf75d4e7):

- [`api/api_image_helper.go`](https://github.com/sndcds/uranus/blob/6fcdb489637001e12c676a9f5a7222cfbf75d4e7/api/api_image_helper.go)
  confirms `main_logo`, `dark_theme_logo`, `light_theme_logo`, `avatar` for both
  organization and venue. Venue additionally supports `main_photo` and
  `gallery_photo_1/2/3`.
- [`ddl/pluto_image.ddl`](https://github.com/sndcds/uranus/blob/6fcdb489637001e12c676a9f5a7222cfbf75d4e7/ddl/pluto_image.ddl)
  confirms UUID identity, `file_name`, `gen_file_name` and nullable text `mime_type`.
  The source reader now selects `mime_type` explicitly.

| rule | entity | severity | Bedeutung |
| --- | --- | --- | --- |
| venue_missing_logo | venue | warning | Kein gültiges main_logo vorhanden |
| organization_missing_logo | organization | warning | Kein gültiges main_logo vorhanden |
| logo_unsupported_format | venue/organization | info | Logo ist weder PNG noch WebP |

The requested quality policy makes **main_logo the required logo**;
**dark_theme_logo / light_theme_logo are optional variants**. This requirement and
format preference are quality policy, not an inferred upstream database constraint.
Allowed formats: **image/png, image/webp**. MIME is authoritative; filename extensions
are never evidence. Comparison trims whitespace and lowercases MIME via
`mime_type.strip().lower()`; `IMAGE/PNG` and ` image/webp ` are allowed. Metadata
retains the original MIME value. NULL/empty/whitespace-only MIME produces no format finding.
No existing general missing-MIME rule exists, so no separate one is introduced.
Avatar, photos, galleries, events and portal logos are excluded from this policy.
A missing image does not satisfy the main-logo requirement and still produces the
separate `image_link_without_image` finding. Missing owners stay with the existing
`image_link_missing_target` rule.

Verification uses synthetic fixtures in a disposable local PostgreSQL/PostGIS database;
repository evidence is not a claim about the deployed schema. These checks only SELECT
source data; persistence writes remain confined to the existing admin storage.


### PR #42 identity correction

Format findings use variant-specific persisted fields: `main_logo.mime_type`,
`dark_theme_logo.mime_type`, `light_theme_logo.mime_type`. IDs follow the existing
URL-encoded `rule:entity_type:entity_key:field` contract, for example
`logo_unsupported_format:venue:<uuid>:main_logo.mime_type`. The separate identity override
has been removed, preserving `admin.finding`'s existing unique identity constraint.
Missing-logo fields/IDs, owner Actions, info severity and rule counts retain their semantics.
No schema migration is introduced for this unmerged rule.

The regression test exercises `run_check()` and real `admin.finding` rows for both
venue and organization, each with three existing images (JPEG/JPEG/SVG). It verifies
three persisted variants, idempotent rescans, resolution of only the repaired dark logo,
resolution of a removed light-logo link, and unchanged states after failed/incomplete scans.

### Postal code whitespace source scope

| rule | entity | severity | Bedeutung |
| --- | --- | --- | --- |
| postal_code_whitespace | organization/venue | warning | Führende oder abschließende Whitespaces in postal_code |

Quality source queries add only `postal_code` from `uranus.organization` and
`uranus.venue`; both columns already exist in the repository's synthetic source DDL
(`tests/fixtures/uranus.sql`). No additional sensitive fields are loaded. This is local
repository/test verification, not a fresh audit of the deployed database.

The check uses `postal_code is not None and postal_code != postal_code.strip()`.
Only boundary whitespace is reported; tabs/newlines at the boundaries are included as
requested (`btrim()` without an explicit character set only removes ordinary spaces).
Internal spaces and tabs remain allowed, including international codes such as `SW1A 1AA`.
No country-specific postal-code format or length is validated and no source value is changed.

The existing quality loader deliberately excludes projections. There is no dedicated
postal-code projection consistency architecture to extend here. Therefore
`event_projection.venue_postal_code` and `event_date_projection.venue_postal_code` are
not scanned or counted separately: their copies must not multiply a venue's finding.
Projection/source divergence diagnostics remain outside this rule.

Synthetic unit tests cover both owner types and the boundary/internal whitespace matrix.
Integration tests run the registered engine and persist findings in `admin.finding`,
checking relevance, one finding per owner despite referencing events/dates, repeated scans,
resolution after correction, counts, and preservation after failed/incomplete scans.

## Notification capability — 2026-09-18

Uranus main `5a5ac813eec708c99de6962aa05a2357535117b0` exports
[`organization.notifications jsonb`](https://github.com/sndcds/uranus/blob/5a5ac813eec708c99de6962aa05a2357535117b0/ddl/organization.ddl).
No production database was queried. The source verifier now reports
`notification_config_capability`; the worker checks it before reading the optional column.
Missing/wrong-type/unreadable capability disables sends without a source migration. Existing
synthetic DDL remains unchanged; disposable tests cover both missing and present capability.
See [notifications](notifications.md) for the strict V1 contract and operator enablement gate.
