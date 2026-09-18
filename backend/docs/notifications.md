# Organization email notifications V1

## Baseline and source verification

Implementation baseline: `uranus-admin/main` **8f0da80327af933de4a7e5237f29e1c4fd5dac49**,
fetched on 2026-09-18, clean worktree. PR #51 is already merged at this baseline;
there is no dependency on an open PR. Branch: `feat/email-notification-system`.

The public Uranus main at **5a5ac813eec708c99de6962aa05a2357535117b0** exports
[`ddl/organization.ddl`](https://github.com/sndcds/uranus/blob/5a5ac813eec708c99de6962aa05a2357535117b0/ddl/organization.ddl)
with `uuid uuid PRIMARY KEY`, `name text NOT NULL`, and **notifications jsonb**.
This is repository evidence, **not production database verification**. The existing
synthetic source fixture intentionally still lacks the column; notification integration
tests add it only to their disposable database. Missing capability is covered separately.

`python -m app.source_schema_verify --json` now reports
`notification_config_capability`. The worker checks catalog visibility and accepts
only a readable JSON/JSONB column before selecting it. Missing/wrong-type/invisible
column means no deliveries; existing relevant notifications become suppressed, and
`/notifications` shows the missing capability. API readiness does not depend on SMTP.
Run the verification with the authorized source reader before enabling delivery.
Never “repair” the source schema through this application.

## Architecture and boundaries

The existing SQLAlchemy engines, admin role preflight, Alembic chain, authenticated
FastAPI router, Nuxt proxy allowlist, Zod contracts, and page components are reused.
The quality source loader and core evaluator supply current ownership/relevance;
persisted findings supply the human review decision. The shared temporal start helper
is also used by quality evaluation. No second job broker or domain ORM is introduced.

- `DATABASE_URL`: source SELECTs, explicit repeatable-read/read-only transactions.
- `ADMIN_DATABASE_URL`: notification state, delivery audit and existing finding reads.
- `ADMIN_MIGRATION_DATABASE_URL`: migration owner only, never used by the worker/API.
- No Uranus INSERT/UPDATE/DELETE/DDL, API token bridge, config editing, or cross-schema FK.
- Organization ownership comes from `event.org_uuid`, venue.org_uuid, or space→venue;
  event-date/link findings inherit the actual event owner. Unknown owners are ineligible.
- Configs are read in keyset pages of 200. Initial source detection is bulk, with indexed
  in-memory grouping, not an event/finding N+1. A pre-send safety check loads only the
  claimed delivery's organization in a fixed number of source queries. No transaction
  spans the global scan or SMTP; planning commits per organization and sending per delivery.
- V1 still materializes the existing bulk quality source snapshot and organization
  history. Monitor memory/history size on large installations; streaming all quality
  data is a shared-engine follow-up, not an invented second architecture.

## Strict JSON contract

```json
{
  "version": 1,
  "recipients": [
    {"email": "operator@example.org", "locale": "de", "enabled": true},
    {"email": "kontakt@example.org", "locale": "da", "enabled": true}
  ],
  "events": {
    "unpublished_upcoming_events": {
      "enabled": true,
      "days_before": 14,
      "reminder": {"enabled": true, "days_after": 7}
    },
    "quality_findings": {
      "enabled": true,
      "minimum_severity": "warning",
      "delivery": "daily_digest"
    }
  }
}
```

Only integer version 1, DE/DA/EN, valid EmailStr addresses, actual JSON booleans/integers,
and known keys are accepted. Unknown nested keys, duplicate addresses (case-insensitive),
unknown locales/versions, and invalid bounds reject the **entire** organization config.
Recipients max 100, days_before 1–365, days_after 1–90. Recipient defaults: de/enabled;
omitted event groups default disabled, reminders default disabled. NULL config means
no subscription. Email validation does not make DNS/deliverability requests. Tests use
`example.test` with email-validator's test mode; production validation stays unchanged.
Errors are isolated per organization, logged by organization ID without raw input,
and displayed to authenticated admins. No best-effort partial sends.

## Storage and grants

Alembic **0008**, parent **0007**, creates only `admin` tables:

| Table | Purpose and key data |
| --- | --- |
| notification | UUID PK, unique semantic dedupe_key, closed type/status, org/entity values, optional finding/rule, typed JSON payload, detection/resolution/expiry/audit timestamps |
| notification_delivery | UUID PK, recipient/locale/email channel/kind/status, subject, semantic fingerprint, immutable JSON snapshot (items + rendered mail), attempts, due/sending/sent timestamps, worker UUID/lease, sanitized error, nullable provider ID |
| notification_delivery_item | Composite delivery_id/notification_id PK; admin-only FKs, delivery CASCADE, notification RESTRICT |

Notification types: `unpublished_upcoming_event`, `quality_finding`. Delivery kinds:
initial/reminder/escalation/digest/test (test is reserved; no public test-send endpoint).
Check constraints enforce states, channel, locales and attempt bounds. Indexes cover
org/status, type/detection time, delivery due state, recipient/sent time, organization,
and reverse item lookups. A partial unique fingerprint index excludes cancelled intents,
allowing a later legitimately re-enabled config to create a replacement.

Revision definitions are frozen; migration code never imports mutable application tables.
Downgrade destroys notification history explicitly. Migration ownership remains
`admin_migrator`; grants follow the repository's separate operator provisioning stage.
Run the updated “after migrations” SQL in `development.md`:

```sql
GRANT SELECT, INSERT, UPDATE ON admin.notification, admin.notification_delivery TO admin_user;
GRANT SELECT, INSERT ON admin.notification_delivery_item TO admin_user;
```

No DELETE, schema CREATE or ownership membership for runtime. Readiness/preflight requires
migration 0008 and all explicit grants; provisioning tests verify real restricted logins.

## State machines

Notification: pending → active / suppressed / resolved / expired. Detection currently
completes its evaluation atomically, so pending is reserved for future staged detection.
A successful send leaves the notification active. Suppressed can become active again.
Resolved/expired can reopen if fresh source evidence makes the same semantic issue relevant.
A persisted payload episode increments on reopening; a recurring issue is a new semantic
occurrence and can send again. Suppression/re-enabling alone does not increment it.

- **resolved**: event released/rescheduled, or successful fresh allowlisted evaluation
  establishes that the quality issue disappeared.
- **expired**: unpublished event has no remaining future start, was removed or moved into
  another non-notifiable state. It was not necessarily repaired.
- **suppressed**: config unavailable/invalid/disabled, no enabled recipients, event outside
  configured window, or quality review/severity makes external delivery ineligible.
- Source errors do not imply resolution; the incomplete collection is not synchronized.

Delivery: queued → sending → sent, or sending → failed → sending. Permanent recipient
rejection or fifth unsuccessful attempt → permanent_failure. Obsolete queued/failed intent
→ cancelled. Sent history is immutable; removed recipients do not delete history. Before
SMTP, current recipients, locale, source state, ownership and reviews are rechecked.
There is inevitably a tiny change-after-read race across independent source/admin/SMTP
systems; source records are never locked for writes to solve it.

## Event reminders

Draft/review plus at least one upcoming start, inclusive `days_until <= days_before`.
Start is evaluated in EVENT_TIMEZONE. Today with all_day or no start_time remains upcoming
all day; otherwise start_time must not have passed. Sort: date ASC, time ASC NULLS LAST,
UUID ASC. This intentionally matches Activity/quality *start* semantics; temporal list
filters that use an event's effective *end* answer a different question.

Dedupe key: `unpublished_upcoming_event:{organization_uuid}:{event_uuid}` (no recipient).
Presentation stages: configured initial window, <=7 important, <=2 urgent, centrally
configurable via NOTIFICATION_IMPORTANT_DAYS / NOTIFICATION_URGENT_DAYS.
The highest current stage wins; no catch-up mail for each skipped stage. A recipient gets
one initial eligible item, an escalation when the stage rises, or a reminder **at least N
24-hour days after the last successful corresponding delivery**, never after the event.
Disabled reminders do not disable stage escalations. A previous send in another locale
still counts; future due mail uses the current recipient locale. No resend solely for a
locale change. Changed dates/titles invalidate queued content.

Compatible event items (org, recipient, locale, kind, stage) share one mail and N audit
items. Urgent/event claims precede quality; urgency cannot be held behind a normal digest.
Reminder fingerprints include the previous successful delivery anchor, never a fresh scan
timestamp. Repeating an unchanged run cannot enqueue another equivalent delivery.

## Quality policy and digests

Only central `EXTERNAL_POLICY` entries are externally renderable:

| Rule | Eligible entity types |
| --- | --- |
| event_without_dates | event |
| event_without_location | event |
| event_date_without_location | event_date |
| url_syntax | event, event_date, event_link, organization, venue, space |
| venue_missing_logo | venue |
| organization_missing_logo | organization |

Everything else is internal, including postal_code_whitespace, all image linkage/identifier/
orphan rules, event_date_space_venue_mismatch and logo_unsupported_format. Unknown rules
cannot render. Only persisted **open** findings which still exist in fresh evaluation are
eligible; in_progress/snoozed/exception/ignored/reviewed/resolved are suppressed. No “reviewed
means approved for email” inference. Newly detected issues await a successful quality check
before first external delivery. Persisted reviews remain authoritative until the check worker
reopens them; the notification worker never edits findings.

Severity threshold and published/upcoming/published_soon priority reasons are both used.
Priority urgent/important/improvement controls entity grouping and friendly emphasis.
One digest per org/recipient/local admin day **at most**, and only when the current nonempty
semantic set differs from the last successful digest. Not a daily or weekly nag.
A removed finding changes a remaining digest; an empty set sends no empty “all clear” mail.

SHA-256 uses sorted notification IDs plus typed semantic payload: finding ID, rule, entity,
severity, relevance, recommendation version and render-relevant names/links. Ignores last_seen,
scan time, raw metadata, source fingerprints and DB order. A new/removed finding, increased
severity/relevance/soon, entity or semantic template revision can produce a new digest. Pure
CSS/whitespace changes do not bump TEMPLATE_VERSION. Item grouping sorts by the entity's
highest priority, entity type/name/key then rule; one entity heading covers its findings.

## Delivery limits, leases and failures

Default max **3 productive emails per recipient per ADMIN_TIMEZONE calendar day across all
organizations**, including in-flight reservations. At most one digest per org/recipient/day.
Short advisory claim lock plus row locks/SKIP LOCKED serialize reservations and claims.
Blocked deliveries keep their rows/items and next_attempt_at moves to next local midnight;
a digest also waits until the configured start hour. DST day boundaries are explicit.
Each `--once` invocation sends at most 100 deliveries; subsequent runs drain durable work.

Queued content is recomposed from validated current data at the first SMTP attempt,
so quota deferral cannot send yesterday’s countdown as a new email. Thereafter body and
RFC Date remain the original composition snapshot across retries.

Each claim has worker_id, lease_until and incremented attempt_count. SMTP runs outside the
transaction with a heartbeat on a separate admin connection. Before SMTP a lost/expired
claim is rejected; completion is fenced by worker ID, state and live lease. Crashed workers'
expired leases can be reclaimed. SMTP accepted → process crash → DB commit missing remains
**at-least-once**: duplicate receipt is possible. A stable
`<notification-delivery-{delivery_uuid}@kulturbytes.de>` helps trace/deduplicate retries but
is not an exactly-once guarantee. A network partition or suspended worker has the same
external side-effect limitation; DB leases cannot revoke an SMTP acceptance.

Retry delays after failures: 5 minutes, 30 minutes, 2 hours, 12 hours; attempt 5 failure
is permanent. Timeout/connection errors and SMTP 4xx retry. Clear SMTP 5xx recipient rejection
is permanent immediately; other errors use the bounded retry schedule. Errors persist only
fixed categories such as smtp_451, never SMTP server text, credentials, sessions or addresses.
No provider message ID is invented. A permanent failure remains visible and does not retry
forever; operators inspect SMTP/configuration and a later meaningful new intent may send.

## Rendering, privacy and security

Shared structure + complete deterministic DE/DA/EN dictionaries. Missing required locale key
falls the *whole message* back to English, preventing mixed fragments; tests require catalogue
key parity. Invalid recipient locales never reach rendering. Dates use localized month names;
today/tomorrow/plurals and draft/review are translated. Helpful wording, event date/name,
organization footer, full plain text and HTML, no marketing/tracking/remote fonts/pixels.

Every mail is multipart/alternative. HTML source values and URLs are escaped; subject control
characters removed, long subjects capped at 180 characters, full names retained in body.
Addresses are validated; headers use EmailMessage and formataddr. STARTTLS defaults on with
normal certificate validation. SMTP secrets use SecretStr and are never API/health/log output.
Links derive from validated ADMIN_PUBLIC_BASE_URL and canonical existing event/finding routes,
never the Host header or arbitrary source URL. No invented notification-settings link.

Recipient PII exists only in authenticated delivery history/snapshots; semantic notifications
contain no addresses. Logs identify organization/delivery and fixed counters/errors, not
recipient labels. Admin previews render inside sandboxed opaque-origin iframes with restrictive
CSP and no script/forms/resources. No v-html. Existing authentication, no-store responses and
SSR auth boundary protect all new routes. Configuration is read-only; no PostgreSQL domain writes.

## Admin API/UI and preview

GET `/api/v1/notifications` supports status, notification_type, organization_id, days,
page/page_size; response includes global active/queued/sent_today/failed counts and capability/
invalid-config diagnostics. GET `/notifications/{id}`, `/notifications/{id}/preview?locale=de|da|en`,
`/notification-deliveries/{id}` are under the same `/api/v1` prefix and require system admin.
Preview reads saved payload and never creates jobs or calls SMTP. Resolved/expired events without a
complete unpublished payload have no event preview. Actual delivery snapshots remain in the audit table.
No POST/test-mail endpoint in V1: no additional mail-relay surface or CSRF exception.

UI `/notifications`, `/notifications/{id}`, `/notifications/deliveries/{id}` offers filters,
counts, status/detail/history, sanitized failures, locale preview HTML/Text and an explicit
Dry Run banner. Browser language never determines recipient locale. Source config errors
and missing capability are visible. The normal GET path never starts detection or sending.

## Environment and deployment

See `backend/.env.example`. Required for delivery: source/admin DSNs, SMTP host and valid
sender, trusted HTTPS admin base URL. Optional SMTP username/password; use a private
EnvironmentFile. Never include migration/operator credentials in the worker service.

1. Deploy code with **NOTIFICATIONS_DELIVERY_ENABLED=false** (default).
2. Run migration using ADMIN_MIGRATION_DATABASE_URL, then explicit runtime grants.
3. Run source verification and the existing quality worker so reviewed persisted findings exist.
4. `uv run python -m app.notification_worker --once` in Dry Run; inspect `/notifications`
   and all three locale previews. No delivery rows or fake sent state are created.
5. Verify SMTP with the operator's controlled staging mailbox/provider procedure. V1 deliberately
   has no arbitrary-recipient test-send endpoint. Automated tests use a fake transport only.
6. Enable delivery explicitly in the worker environment after review; restart/reload the
   appropriate services. Keep API/worker feature flags consistent so the banner reflects reality.
7. Observe initial batches, sanitized errors, queued age and permanent failures. SMTP outage
   never prevents candidate detection and is not a general API readiness blocker.

Example hardened hourly timer (adjust service user, paths and clock window):

```ini
# /etc/systemd/system/uranus-admin-notification-worker.service
[Unit]
Description=Kulturbytes organization email notifications
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=uranus-admin
Group=uranus-admin
WorkingDirectory=/srv/uranus-admin/backend
EnvironmentFile=/etc/uranus-admin/worker.env
Environment=UV_CACHE_DIR=/var/cache/uranus-admin
ExecStart=/usr/local/bin/uv run --frozen --no-sync python -m app.notification_worker --once
CacheDirectory=uranus-admin
ReadWritePaths=/var/cache/uranus-admin
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
UMask=0077

# /etc/systemd/system/uranus-admin-notification-worker.timer
[Unit]
Description=Check organization notifications hourly
[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=120
Unit=uranus-admin-notification-worker.service
[Install]
WantedBy=timers.target
```

Install Python dependencies during deployment, before ProtectSystem=strict runtime.
No-sync avoids runtime environment mutation; the dedicated uv cache path stays writable.
Alternatively run the standalone loop (default poll 3600 seconds). Digest eligibility begins
at NOTIFICATION_QUALITY_START_HOUR in ADMIN_TIMEZONE (default 08:00); event checks are independent.
EVENT_TIMEZONE controls days_until; URANUS_TIMESTAMP_TIMEZONE remains for existing naive source
creation timestamps and is never inferred from server timezone.

## Retention and follow-ups

No automatic deletion in V1. Plan operator-reviewed 180/365-day retention of recipient PII and
snapshots with explicit archival/audit requirements; runtime deliberately lacks DELETE.
Monitor growth until that policy is agreed. Backups must follow the same access/retention policy.
Future work: provider bounces, delivery failure operator retry workflow, authorized Uranus API
config editing, recipient self-service, larger-source streaming, optional authenticated and
rate-limited test mail, localization review by native speakers. No weekly unchanged digest,
SMS/push/WhatsApp/newsletter/AI-generated runtime text/custom cron or template editor in V1.
