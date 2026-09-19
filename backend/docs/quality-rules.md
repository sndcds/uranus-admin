# Quality Rules v2

## Audit and boundaries

Admin base: `2f7b794751eddcee4713bf276f3978a8d752be7d` (main, PR #57).
Uranus main audited: `15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e`.
The authoritative schema is the [DDL at that commit](https://github.com/sndcds/uranus/tree/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/ddl).
These checks address patterns reported from real-data analysis, not particular
records or production counts. No dump, production UUID, name, address or token
was used in fixtures or committed. Fixtures are synthetic and are not DDL evidence.

All 22 new rules are **internal only**. `EXTERNAL_POLICY` remains unchanged;
severity never grants notification eligibility. There are no automatic fixes,
Uranus writes, source DDL, migrations, admin grant changes or new configuration.
No HTTP, SMTP, geocoding, DNS/MX lookup or other external network request occurs
in these rules. Database access remains the existing read-only source snapshot.

## Rule catalog

The existing catalog and lifecycle contract remain in
[source verification](source-verification.md) and [contracts](contracts.md).
The following rows are additions, not replacements for existing rules.

| Rule                                     | Entity                                    | Field                                        | Severity | Meaning                                                                                                                       | External notification? | Auto-fix? | Notes                                                                                               |
| ---------------------------------------- | ----------------------------------------- | -------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------- | --------------------------------------------------------------------------------------------------- |
| `event_date_end_before_start`            | event_date                                | end_date                                     | error    | Das Enddatum liegt vor dem Startdatum.                                                                                        | no                     | no        |                                                                                                     |
| `event_date_same_day_end_before_start`   | event_date                                | end_time                                     | error    | Die Endzeit liegt am selben Tag vor der Startzeit.                                                                            | no                     | no        | Requires explicit end_date = start_date; never fires for NULL end_date.                             |
| `event_date_overnight_without_end_date`  | event_date                                | end_date                                     | info     | Die Endzeit liegt vor der Startzeit. Falls der Termin über Mitternacht geht, sollte ein explizites Enddatum angegeben werden. | no                     | no        | Ambiguity hint only; does not change existing list end-time semantics.                              |
| `event_price_without_currency`           | event                                     | currency                                     | warning  | Ein Preis ist angegeben, aber die Währung fehlt.                                                                              | no                     | no        |                                                                                                     |
| `event_price_range_invalid`              | event                                     | min_price / max_price / price                | error    | Der Preisbereich ist ungültig.                                                                                                | no                     | no        | Separate stable fields for each negative bound and reversed range; reason codes below.              |
| `event_free_with_price`                  | event                                     | price_type                                   | warning  | Die kostenlose Veranstaltung enthält eine Preisangabe.                                                                        | no                     | no        | Even an explicit zero price is a stored price; NULL is absence.                                     |
| `event_link_empty`                       | event_link                                | url                                          | warning  | Der Veranstaltungslink enthält keine URL.                                                                                     | no                     | no        |                                                                                                     |
| `event_link_missing_type`                | event_link                                | type                                         | info     | Dem Veranstaltungslink fehlt ein Typ.                                                                                         | no                     | no        | DDL nullable; current update API requires type.                                                     |
| `event_link_unknown_type`                | event_link                                | type                                         | warning  | Der Veranstaltungslink verwendet einen unbekannten Typ.                                                                       | no                     | no        | Trim before vocabulary lookup; optional blank handled separately.                                   |
| `email_syntax`                           | organization / venue / event              | contact_email / registration_email           | warning  | Die E-Mail-Adresse ist syntaktisch ungültig.                                                                                  | no                     | no        | Optional blank accepted; no identity/login email inspection; syntax only.                           |
| `postal_code_syntax`                     | organization / venue                      | postal_code                                  | warning  | Die Postleitzahl hat ein ungültiges Format.                                                                                   | no                     | no        | DE/DEU: 5 ASCII digits; DK/DNK: 4. Other countries: conservative character check.                   |
| `text_surrounding_whitespace`            | organization / venue / event / event_link | selected structured fields                   | info     | Das strukturierte Feld enthält führende oder abschließende Leerzeichen.                                                       | no                     | no        | Excludes descriptions, postal_code and other free text.                                             |
| `space_capacity_inconsistent`            | space                                     | seating_capacity                             | warning  | Die Sitzplatzkapazität ist größer als die Gesamtkapazität.                                                                    | no                     | no        |                                                                                                     |
| `space_capacity_invalid`                 | space                                     | total_capacity / seating_capacity / area_sqm | error    | Kapazität oder Fläche ist negativ.                                                                                            | no                     | no        |                                                                                                     |
| `released_event_without_description`     | event                                     | description                                  | warning  | Die veröffentlichte Veranstaltung hat keine Beschreibung.                                                                     | no                     | no        | Publication relevance reused from QualityContext; released/rescheduled.                             |
| `released_event_without_categories`      | event                                     | categories                                   | warning  | Die veröffentlichte Veranstaltung hat keine Kategorie.                                                                        | no                     | no        | Publication relevance reused from QualityContext; released/rescheduled.                             |
| `released_event_without_type`            | event                                     | event_type_link                              | warning  | Die veröffentlichte Veranstaltung hat keinen Veranstaltungstyp.                                                               | no                     | no        | Publication relevance reused from QualityContext; released/rescheduled.                             |
| `membership_joined_accept_token_present` | team_membership                           | accept_token                                 | error    | Eine bereits angenommene Team-Einladung besitzt noch einen aktiven Einladungstoken.                                           | never                  | no        | Composite membership key; boolean evidence only. Organization action; excluded by active Geo Scope. |
| `event_unknown_category`                 | event                                     | categories                                   | warning  | Die Veranstaltung verwendet eine unbekannte Kategorie.                                                                        | no                     | no        |                                                                                                     |
| `event_type_link_unknown_type`           | event                                     | event_type_link                              | warning  | Die Veranstaltung verwendet einen unbekannten Veranstaltungstyp.                                                              | no                     | no        | One finding per event; unknown IDs aggregated. Genre 0 is allowed.                                  |
| `event_type_link_unknown_genre`          | event                                     | event_type_link                              | warning  | Die Veranstaltung verwendet ein unbekanntes Genre.                                                                            | no                     | no        | One finding per event; unknown IDs aggregated. Genre 0 is allowed.                                  |
| `event_unknown_language`                 | event                                     | languages                                    | warning  | Die Veranstaltung verwendet einen unbekannten Sprachcode.                                                                     | no                     | no        |                                                                                                     |

Existing `organization_missing_location` and `venue_missing_location` remain
warning findings on `point`, with `geocode_supported=true`. They already shipped
on the audited admin main (Geo Phase 3); no duplicate implementation was added.
There were no open PRs at the start of this audit.

`event_price_range_invalid` reasons: `negative_min_price`, `negative_max_price`,
`min_greater_than_max`. Capacity reasons: `negative_total_capacity`,
`negative_seating_capacity`, `negative_area_sqm`. Messages explain these reasons
in German without requiring the frontend to render raw metadata.

Email validation reuses `email-validator`, the existing dependency behind
Pydantic `EmailStr`, with deliverability disabled. Test-environment syntax permits
reserved `.test` examples. Optional whitespace-only values are not syntax errors.
Metadata contains `field` and a fixed `reason`, never the address itself.

Postal syntax trims edge whitespace before validating: `24937` produces only
the existing `postal_code_whitespace`. `24937^` has two independent defects.
Internal spaces/hyphens and alphanumeric international codes remain allowed for
unknown countries; other characters, including embedded controls, are rejected.
Country names are not guessed into ISO codes. `country.code`/`geolist_country.code`
are three-character catalogs; organization country is free text, venue country
is `character(3)`. DE/DK aliases are also accepted for synthetic/legacy inputs.

Structured whitespace checks cover organization/venue street, house_number,
city, country, state; event registration_email, registration_phone, currency;
and event_link type/url. Postal-code whitespace retains its existing rule.

## Verified source columns

Every column below was checked against its current `ddl/<table>.ddl`, including
type, nullability, constraints and relationships. This is the complete explicit
core-quality projection contract, including pre-existing columns. The local
[source manifest](../app/source_contract.py) records PostgreSQL type names.
Aliases do not introduce additional source fields.

| Table                      | Source columns                                                                                                                                                                                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `organization`             | `uuid`, `name`, `street`, `house_number`, `address_addition`, `postal_code`, `city`, `country`, `state`, `point`, `web_link`, `contact_email`                                                                                                                                         |
| `venue`                    | `uuid`, `name`, `org_uuid`, `street`, `house_number`, `postal_code`, `city`, `country`, `state`, `osm_id`, `point`, `web_link`, `ticket_link`, `contact_email`                                                                                                                        |
| `space`                    | `uuid`, `name`, `venue_uuid`, `web_link`, `total_capacity`, `seating_capacity`, `area_sqm`                                                                                                                                                                                            |
| `event`                    | `uuid`, `title`, `org_uuid`, `venue_uuid`, `space_uuid`, `release_status`, `source_link`, `online_link`, `ticket_link`, `registration_link`, `registration_email`, `registration_phone`, `min_price`, `max_price`, `currency`, `price_type`, `description`, `categories`, `languages` |
| `event_date`               | `uuid`, `event_uuid`, `venue_uuid`, `space_uuid`, `release_status`, `start_date`, `start_time`, `end_date`, `end_time`, `all_day`, `ticket_link`                                                                                                                                      |
| `event_link`               | `id`, `event_uuid`, `type`, `url`                                                                                                                                                                                                                                                     |
| `event_type_link`          | `event_uuid`, `type_id`, `genre_id`                                                                                                                                                                                                                                                   |
| `event_category`           | `category_id`                                                                                                                                                                                                                                                                         |
| `event_type`               | `type_id`                                                                                                                                                                                                                                                                             |
| `genre_type`               | `genre_id`                                                                                                                                                                                                                                                                            |
| `language`                 | `code_iso_639_1`                                                                                                                                                                                                                                                                      |
| `link_type`                | `key`                                                                                                                                                                                                                                                                                 |
| `organization_member_link` | `org_uuid`, `user_uuid`, `has_joined`, `accept_token`                                                                                                                                                                                                                                 |
| `license`                  | `key`, `url`                                                                                                                                                                                                                                                                          |
| `pluto_image`              | `uuid`, `created_at`, `mime_type`                                                                                                                                                                                                                                                     |
| `pluto_image_link`         | `context`, `context_uuid`, `identifier`, `pluto_image_uuid`                                                                                                                                                                                                                           |

`organization_member_link.accept_token` is **never returned as a value**:
SQL projects `(accept_token IS NOT NULL AND btrim(accept_token) <> '') AS
accept_token_present`. The snapshot has only org_uuid, user_uuid, has_joined and
that boolean. Unique `(org_uuid,user_uuid)` establishes the existing
`membership:<org_uuid>:<user_uuid>` entity key. Neither fingerprint nor ID
includes the token. Password hashes, activation/import/reset/refresh token
values and private messages are absent from the quality projection.

Source constraints are respected: event_link.url is NOT NULL but permits blank;
its type is nullable and has no vocabulary FK. Event categories/languages are
nullable arrays. event_type_link has a composite unique key and an event FK but
no type/genre vocabulary FKs; genre_id defaults to 0. Vocabulary translations
are reduced to distinct IDs/codes, not counted as separate definitions.
Point columns are nullable `geometry(Point,4326)`. Prices and capacity fields
are nullable and have no DDL checks against the inconsistencies reported here.
Dates retain nullable times/end_date, mandatory start_date and existing
venue/space inheritance. No constraint violations are manufactured in tests.

## Product evidence beyond DDL

All links refer to the audited Uranus SHA, not a moving branch:

- [Team invite acceptance](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/api/admin_org_team_invite.go)
  explicitly sets has_joined=true and accept_token=NULL.
- [Event model](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/model/event.go)
  defines the free price type. Its ticket flag constants do **not** define
  ticket_required or registration_required.
- [Event read contract](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/sql/admin-get-event.sql)
  reads categories, languages, registration fields and pricing from event.
  [Creation validation](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/api/admin_create_event.go)
  specifies ISO-639-1 languages; old write SQL in this file still uses event_id
  in places and is **not** treated as the current schema contract.
- [Event type lookup](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/sql/admin-get-event-types.sql)
  joins event_type_link against event_type/genre_type IDs.
- [Link update payload](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/api/admin_update_event_links.go)
  requires type; [choosable link types](https://github.com/sndcds/uranus/blob/15835d8ac0f217e53fa5e8ee7b451a1ed6bd6c2e/api/get_choosable_link_types.go)
  reads link_type_i18n, whose DDL FK references link_type.key.

## Deliberately deferred or rejected candidates

| Candidate                                                                              | Decision / evidence                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| event_ticket_required_without_ticket_link; event_registration_required_without_contact | Deferred. event.ticket_flags is a user-defined enum array, but this DDL tree omits CREATE TYPE labels and the current Go constants contain neither required flag. Do not import values from the dump or synthetic fixtures. Confirm the current enum/product contract first, then add event/date ticket-link sets and contact checks. |
| event_date_all_day_with_time                                                           | Not implemented: current admin_update_event_dates.go requires start_time even when AllDay is present. This combination is supported by the current payload and must not be diagnosed as inconsistent.                                                                                                                                 |
| portal_geometry_filter_without_geometry                                                | Rejected: sql/portal-condition.sql explicitly accepts NULL geometry as unrestricted, including geometry filter modes.                                                                                                                                                                                                                 |
| portal_allowlist_filter_without_entries                                                | Deferred: an empty allowlist yields no results, but no product requirement forbids an intentionally empty portal.                                                                                                                                                                                                                     |
| portal_blocklist_filter_without_entries                                                | Rejected: an empty blocklist legitimately excludes no organization.                                                                                                                                                                                                                                                                   |
| Pending membership without token                                                       | Deferred: schema/workflow does not prove every nonjoined membership must be an active invitation.                                                                                                                                                                                                                                     |
| Missing content language / event languages / organization or venue language            | Deferred: optional fields and potentially systemic migration/product state; existing nonempty language codes can still be validated.                                                                                                                                                                                                  |
| venue_type_unspecified; space_type_missing                                             | Deferred: optional/default model, no universal completeness requirement established.                                                                                                                                                                                                                                                  |
| Username missing; user locale missing                                                  | Deferred: optional identity/product contract, not content quality.                                                                                                                                                                                                                                                                    |
| expired_password_reset_token                                                           | Operations follow-up, not a content finding. password_reset.token alone is unique; multiple rows per user are permitted. A per-user aggregate diagnostic can use user_uuid/expires_at without token values, but must first define aggregation and operator UX. No password-reset columns are loaded by this PR.                       |
| social_post_stuck_pending                                                              | Operations follow-up: current social_post_destination DDL confirms UUID, pending/success/failed, aware created_at and retry_count. Introduce a separate bounded operations diagnostic with a 24h configurable threshold, rather than adding maintenance counts to content completeness. No config or source query is added here.      |
| Failed social destinations; expired refresh tokens                                     | Not added: pending-age is distinct from failure handling; no verified retention contract requires removal of expired refresh-token history.                                                                                                                                                                                           |

The legacy `portal` table is not used. `portal2`, `portal_temp`, both portal lists,
social_post, social_post_destination, password_reset, country/geolist_country,
currency and the vocabularies were inspected; only needed tables are queried.
No production SQL dump was imported to resolve ambiguous enum semantics.

## Lifecycle, priority, UI and Geo Scope

All new normal rules participate in CORE_RULES and therefore check-run rule_count,
finding_count, dashboard counts and persisted filtering. Team-token integrity is
an internal data-integrity finding, grouped under **Interne Sicherheit** in the
quality overview. Existing dashboard totals already include queue findings; they
remain a mixed quality/workflow total, not a pure content-completeness metric.
Operations retention diagnostics are deliberately kept out of those totals.

Identity remains `rule + entity_type + entity_key + field`. Each rule covers
clean and dirty entities so successful rechecks resolve repaired findings.
Relevant field-specific evidence is hashed into source_fingerprint; observation
time, priority aging and unrelated fields do not change new-rule fingerprints.
Changed evidence reopens an exception/ignored finding through existing persistence.
Incomplete or failed runs cannot resolve previous findings. A rule exception
continues to fail the run safely; there is no exception-swallowing fallback.
Adding projected fields can change fingerprints of **older** rules, which hash
the whole existing row; their reviewed exceptions may reopen once after rollout.

QualityContext.relevance and priority_details retain released/rescheduled and
upcoming/soon semantics. No parallel priority engine was added. Date-order rules
do not change temporal list filters or effective venue/space inheritance.

Existing string rule/entity filters accept the new IDs within their
length bounds; no API/Pydantic/Zod/proxy/OpenAPI change is required. German labels
use the existing quality utility and findings render German messages. Unknown
vocabulary IDs are safe minimal metadata; contact values are not duplicated.
Entity actions use existing routes. Membership findings link to the known
organization; event links have no fabricated detail route.

Active Geo Scope uses existing membership: spatial events, dates, organizations,
venues and spaces are filtered; team_membership and event_link are nonspatial.
Missing-location findings lack an authoritative point and stay excluded.
No Nominatim candidate becomes authoritative or is copied into findings.

## Complexity and diagnostics

The source loader now performs 17 fixed bulk SELECTs (previously 10): new sets
for event_type_link, four vocabularies plus link_type, and membership booleans.
No per-event/date/finding query is introduced. QualityContext builds type/genre
links by event and distinct vocabulary sets once. Runtime and memory remain
O(source rows + array elements) for the fixed rule catalog. Output sorting for
stable metadata is bounded by each entity's distinct unknown values.

The existing operator command is extended:

```sh
cd backend
uv run python -m app.source_schema_verify --json
```

It requires an authorized reader and does not access GitHub. `source_contract`
reports `diagnostic=source_schema_drift`, `capability=quality_snapshot`,
`compatible`, the audited SHA, missing_tables, missing_columns and type_mismatches.
Missing visible required columns have category `missing_required_source_column`;
type failures use `source_type_mismatch`. UUID, arrays, enum type names,
date/time/timestamp and Point/4326 assumptions are checked. Additional/legacy
columns and tables are ignored. Enum **label** sets, full nullability equivalence,
all application queries and full DDL equivalence are not claimed by this bounded
manifest. Existing broader metadata/notification-capability reporting remains.
The CLI exits 1 on drift or sanitized connection failure, 0 on compatibility.
`/ready` remains unchanged; operators should run this diagnostic before rollout.
No new persistence or admin grants are introduced. Existing installations using
the documented explicit reader allowlist need SELECT on uranus.language and
uranus.link_type; provisioning instructions include these two vocabulary tables. Catalog visibility still depends
on the reader's actual privileges; role names are not evidence of compatibility.

## Validation and follow-ups

Synthetic tests cover temporal boundaries/overnight, pricing, capacity, published
completeness, vocabularies, email/postal syntax, whitespace deduplication, member
token booleans, scoped snapshots, constant query count, policy exclusion, API/log
leak prevention, persistent resolution/review invalidation, partial-run safety,
Geo Scope and schema drift/extra tables. Frontend tests cover labels/groups and
membership filter/action drilldown in Chromium, including production CSP tests.
The PR records exact full-suite and CI results; fixtures do not prove live schema
compatibility. No production database was accessed for this audit.

After explicit product review, date order and public content-completeness rules
could join EXTERNAL_POLICY in a separate PR. Membership/schema/maintenance rules
must remain internal. Any remediation remains manual; a future automated fix
requires a verified, authorized Uranus API contract, never direct SQL writes.
