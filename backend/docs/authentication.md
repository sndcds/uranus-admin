# Eigenständige Admin-Authentifizierung

## Entscheidung und vorherige Uranus-Analyse

Die Folgeanweisungen zu Issue #2 ersetzen die ursprünglich geplante Uranus-Identity-Integration:
**Eigene Konten in FastAPI, separate Berechtigungstabelle in `admin`, kein Uranus-Status-Lookup
und keine Änderung im Repository `sndcds/uranus`.** Uranus-Credentials werden nicht akzeptiert.
Ein normales Uranus-Konto, eine Organisation-Owner-Rolle oder vollständige Organisationsrechte
begründen weder eine lokale Identität noch globale Admin-Rechte.

Vor dieser Entscheidung wurden Uranus-Login, Middleware, JWTs, Refresh/Logout, Profil, User-DDL
und sämtliche vorhandenen Permission-Bits/Grant-Tabellen geprüft. Referenz: gemergter Stand
[`3ce5ea45`](https://github.com/sndcds/uranus/tree/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7),
lokal gelesener Refresh-Commit `12ec7608`. Belegte Eigenschaften:

- `POST /api/login` prüft Passwort und `is_active`; stellt HS256-Access- und Refresh-JWTs aus.
- `app.ParseJWT` prüft HS256, Signatur, erforderliches `exp` und `nbf`; Middleware verlangt
  `token_type=access` und eine nichtleere UUID. `iss`/`aud` werden nicht als Vertrag validiert.
- Access-Laufzeit ist bei Neuausstellung auf maximal 900 Sekunden begrenzt; Refresh-Default
  sieben Tage. Refresh-Rotation und Logout betreffen registrierte Refresh-Familien; bereits
  ausgegebene Access-Tokens bleiben bis zu ihrem Ablauf gültig.
- `GET /api/admin/user/profile` liefert ein Profil, aber prüft nicht den aktuellen Aktivierungsstatus.
- Das User-Modell kennt `is_active` und physische Löschung; keine zusätzlichen Sperrfelder erfinden.
- Permission-Bits und `UserPermCombinationAdmin` betreffen Organisationen/Objekte; die
  User-Organisation-/Venue-/Space-/Event-Links und Partner-Grants enthalten keine globale Rolle.

Quellen: [JWT](https://github.com/sndcds/uranus/blob/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7/app/jwt.go),
[Middleware](https://github.com/sndcds/uranus/blob/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7/app/middleware.go),
[Token-Lebenszyklus](https://github.com/sndcds/uranus/blob/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7/api/auth_tokens.go),
[Profil](https://github.com/sndcds/uranus/blob/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7/api/admin_user_profile.go),
[Permissions](https://github.com/sndcds/uranus/blob/3ce5ea45e0c3333b52ff0af1e6cb3263fb8063c7/app/permissions.go).
Diese Verträge werden durch die jetzige Implementierung **nicht aufgerufen oder nachgebaut**.

## Authentication und Authorization

**Authentication:** `admin.auth_account` enthält unabhängige Konto-UUID, normalisierten Login
(trim/casefold), Argon2id-Passworthash, `is_active` und eine Credential-Version. Neue Konten sind
standardmäßig inaktiv. Es gibt keine öffentliche Registrierung, keine Passwort-Reset-Mails und
keine Kontoverwaltungs-API. Passwörter werden nur beim Login transient verarbeitet; keine Kopien
von Uranus-Hashes und keine Speicherung von Klartextpasswörtern.

**Authorization:** `admin.auth_system_admin` erlaubt Operations und Recherche;
`admin.auth_journalist` erlaubt ausschließlich Recherche. Beide Grants speichern Vergabezeit
und DB-Operator und können unabhängig nebeneinander bestehen. Ohne Grant besteht trotz
korrektem Passwort kein Workspace-Zugriff. Die Runtime darf Konto und Grants nur lesen;
ausschließlich der getrennte Betreiberzugang verwaltet sie.

`get_identity()` authentifiziert eine Sitzung. `get_current_admin()` verlangt den
Systemadmin-Grant für Operations. `/api/v1/research/*` und `/auth/session` verwenden
`get_current_research_user()` und erlauben Systemadmin oder Journalist. Aktive Konten ohne
Grant erhalten dort 403. Der Login darf weiterhin eine normale Identität bestätigen;
dies gewährt allein keinen Workspace-Zugriff.

## Production-Flow und HTTP-Vertrag

```text
Browser → gleiche Origin /api/admin/auth/login → Nuxt/Nitro → FastAPI /auth/login
Browser ← HttpOnly-Sitzungscookie + {subject, system_admin, journalist}
Browser → /api/admin/api/v1/... → Nitro → FastAPI
                                      → Sitzung und aktives Admin-Konto prüfen
                                      → passenden Workspace-Grant prüfen
```

- `POST /auth/login`: JSON `{login, password}`. Erfolg 200; Antwort enthält ausschließlich
  `subject`, `system_admin` und `journalist`. Ein neuer zufälliger Sitzungswert kommt ausschließlich als
  HttpOnly-Cookie, niemals im JSON, HTML, SSR-State oder einem Browser-Speicherobjekt an.
- `GET /auth/session`: servervalidierte Workspace-Identität, 200 mit `subject`, `system_admin`
  und `journalist`; 401 ohne gültige Sitzung, 403 ohne Workspace-Grant.
  `Cache-Control: private, no-store`; keine Passworthashes oder Sitzungswerte.
- `POST /auth/logout`: widerruft die aktuelle Sitzung in der Datenbank und löscht das Cookie.
  Ohne Credential (mit Origin/CSRF) idempotent 200; DB-Fehler melden keinen erfolgreichen Widerruf.
- Ohne Credential: 401 `authentication_required`. Ungültig/manipuliert/abgelaufen oder inaktives/
  gelöschtes Konto: 401 `invalid_credentials`. 401 behält `WWW-Authenticate: Bearer`.
- Aktives Konto ohne passenden Grant: 403 `admin_access_denied` für Operations,
  `research_access_denied` für Recherche und `/auth/session`. Fehlerhafte Browser-Provenienz:
  403 `csrf_rejected`. Zu viele Loginversuche: 429 `login_rate_limited`.
- Fehlende Login-Origin/Admin-Ablage: 503 `admin_auth_unconfigured`. Nicht erreichbare oder
  unzureichend provisionierte Auth-Ablage: 503 `auth_storage_unavailable`. Ein vom Boundary-Check
  abgelehnter DB-Account liefert weiterhin 503 `admin_storage_unconfigured`.
- Es gibt keine neuen JWTs, Refresh-Tokens, Signing Keys, JWKS- oder Introspection-Endpunkte.
  Fremde JWTs/Refresh-Tokens sind ungültige Admin-Credentials. `URANUS_API_URL` wird nicht zur Authentifizierung verwendet; siehe Activity-Previews im API-Vertrag.

## Sitzungen, CSRF und Secrets

Sitzungen sind kryptographisch zufällige 256-Bit-Werte; PostgreSQL speichert nur SHA-256-Digests
in `admin.auth_session`. Absolute Laufzeit standardmäßig 3600 Sekunden, Inaktivitätsgrenze
900 Sekunden, serverseitig geprüft. Aktivität verlängert nur die Inaktivitätsfrist, niemals die
absolute Laufzeit. Das nichtpersistente Browser-Cookie hat kein Max-Age; nach Ablauf ist eine
neue Passwortanmeldung nötig. Es findet kein automatischer Refresh statt.

Jeder Request prüft das aktive Konto, Credential-Version, Widerruf, beide Ablaufgrenzen und die
aktuelle Berechtigung. Logout, Passwortwechsel, Sperrung und CLI-Rechteänderungen widerrufen
Sitzungen. Berechtigungsentzug wird unabhängig davon live aus der separaten Tabelle gelesen.
Bereits autorisierte laufende Requests können noch abschließen; nachfolgende Requests werden
abgelehnt. Direkte DB-Passwortänderungen müssen die Credential-Version erhöhen; das CLI erledigt
Versionserhöhung und Widerruf atomar.

Die öffentliche Admin-Origin muss HTTPS verwenden. Zwischen Nitro und FastAPI laufen auch
Passwörter und Sitzungscookies: Loopback auf demselben Host verwenden oder die Verbindung
verschlüsseln (HTTPS bzw. einen authentifizierten verschlüsselten Transport). Ein entfernter
unverschlüsselter HTTP-Upstream über ein ungeschütztes Netz ist keine sichere Production-Konfiguration.

Production/Staging verwenden `__Host-admin_session`: Secure, HttpOnly, SameSite=Strict, Path=/,
kein Domain-Attribut. Development/Test verwenden `admin_session` ohne Secure für lokales HTTP.
Für Login, Logout und Cookie-authentifizierte Schreibrequests verlangt FastAPI die exakte
`AUTH_PUBLIC_ORIGIN` und `X-Admin-CSRF: 1`. SameSite ist zusätzliche Absicherung, kein Ersatz
für diese Prüfung. Bearer-Aufrufe benötigen kein Cookie-CSRF, dürfen aber nur denselben gültigen
Sitzungswert bzw. den ausdrücklich lokalen Dev-Override enthalten. Keine Credentials in URLs.

Nitro leitet nur das zur Build-Umgebung passende Sitzungscookie, explizites Authorization,
Origin und den vorgesehenen CSRF-Header weiter; kein vollständiger Cookie-/Header-Satz. Auth-
Erfolgsantworten werden vor Weitergabe streng auf den erlaubten Inhalt geprüft. Antworten
sind `private, no-store` und variieren nach Authorization/Cookie/Origin. Browserdaten werden bei
Auth-Verlust verworfen; erfolgreiche Neuanmeldung löst einen neuen Abruf aus.

Argon2id verwendet 64 MiB, drei Durchläufe, Parallelität zwei. Kontoanlage verlangt 15–1024 Zeichen,
keine stillschweigende Kürzung. Unbekannte Logins erhalten eine Dummy-Hash-Prüfung. Datenbank-
Limits gelten zuerst pro Quelle (20 Versuche/5 Minuten), dann pro normalisiertem Login
(zehn/5 Minuten), zuletzt als Überlastsicherung global (1200/5 Minuten), über alle Worker.
Abgewiesene Quellen verbrauchen keine weiteren Login- oder globalen Slots. Je Worker sind maximal vier gleichzeitige Passwortprüfungen zugelassen.
Limits schützen die Hash-Prüfung, ersetzen aber kein vorgelagertes Request-/Body-Limit.

Auth-Fehler enthalten keine Credentials, Roh-DB-Fehler oder verketteten Driver-Exceptions, auch
bei APP_DEBUG. Keine Header-/Body-/Cookie-Logs an Proxy oder FastAPI aktivieren. Private Hashes
und DB-Zugänge bleiben ausschließlich serverseitig. Kontoänderungen geben nur Aktion/UUID aus. `app.auth.manage doctor` zeigt zusätzlich
sichere DB-/Rollen- und Preflight-Statusinformationen, niemals die DSN.

Grundlagen: [Argon2 PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html),
[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Betrieb und Grenzen

Provisionierung, Migration `0004`, Operator-Grants und CLI-Befehle stehen in
[development.md](development.md#eigenständige-admin-authentifizierung-migration-0004).
`ADMIN_DATABASE_URL` genügt für Auth; `DATABASE_URL` wird dabei weder für Identität noch Status
abgefragt. Fachliche Reporting-Routen benötigen weiterhin ihren getrennten Uranus-Reader.
`ADMIN_MIGRATION_DATABASE_URL` bleibt ausschließlich Alembic. Kein automatisches Schema-Upgrade.

Audit-Identität ist `admin:<eigene UUID>`. Sie wird in `reviewed_subject`, Markierungsautoren und
Abschlussautoren gespeichert. Sie ist keine Uranus-User-UUID: `reviewed_by` wird daraus nicht
befüllt. Die fachliche Zuweisung `assigned_to` behält ihren bisherigen Uranus-Vertrag und vergibt
keine Rechte. Dev-Identität `development-only` ist ausschließlich lokal möglich.

`DEV_AUTH_ENABLED=true` benötigt `APP_ENV=development|test` und den expliziten Dev-Token.
Staging/Production lehnen diese Konfiguration beim Start ab und prüfen zusätzlich die Umgebung
in der Dependency. Eine Frontend-Einstellung kann diese Grenze nicht ändern.

Uranus-Kontosperrung oder -Löschung deaktiviert das unabhängige Admin-Konto nicht automatisch.
Beim Entzug des Admin-Zugangs muss der Betreiber das Admin-Konto separat sperren bzw. dessen
globale Vergabe entziehen. Genau dafür stehen die CLI-Aktionen `disable` und `revoke` bereit.

Kein MFA, SSO oder Self-Service-Passwortreset in dieser Umsetzung. Kontowiederherstellung erfolgt
über das Betreiber-CLI. PostgreSQL ist gemeinsamer Sitzungs-/Limit-Speicher für alle API-Worker;
es gibt keinen flüchtigen prozesslokalen Sitzungsspeicher. Abgelaufene Sitzungen und Limit-Buckets
müssen betrieblich bereinigt werden. Absichtliche Loginversuche können das zeitlich begrenzte
Limit eines Kontos auslösen; Betreiber können die Bucket-Zeile kontrolliert entfernen.

## Login-Limits: Quelle, Proxy-Vertrauen und Speichergrenze

FastAPI verwendet ausschließlich `Request.client.host`, keine selbst geparsten Forwarded-Header.
Direkter Betrieb: Uvicorn mit `--no-proxy-headers`. Hinter Nitro: `--proxy-headers` und
`--forwarded-allow-ips=<exakte Nitro-Peer-IP>`; niemals `*`. FastAPI nur für diesen Proxy
bzw. das private Netz erreichbar machen. Nitro ersetzt X-Forwarded-For durch eine einzelne
validierte IP aus dem Socket. Vom Browser gelieferte XFF-Ketten werden nie weitergereicht.

Bei vorgeschaltetem Nginx muss `NUXT_TRUSTED_INGRESS_IPS` ausschließlich dessen tatsächliche
Socket-Peer-IPs enthalten (kommagetrennt, inklusive IPv4-mapped IPv6 falls verwendet).
Nur von diesen Peers übernimmt Nitro `X-Real-IP`. Der Ingress muss diesen Header mit der
verifizierten Client-IP **überschreiben**, niemals einen Client-Header übernehmen. Ohne diese
explizite Konfiguration teilen Nutzer hinter einem Proxy dessen Quellenlimit. Die Defaultliste
ist leer. Diese Einstellung verändert keine Live-Proxy-Konfiguration.

Login und Quelle werden unabhängig auf jeweils 65536 SHA-256-Partitionen abgebildet.
Damit können neue Versuche höchstens 131073 Bucket-Zeilen erzeugen, auch ohne Cleanup.
Kollisionen verschärfen Limits konservativ; sie umgehen keine Limits und verraten keine Konten.
IPv6-Adressen zählen als einzelne Quellen; verteilte Angriffe trifft weiterhin die globale Grenze.
Ein gezielter Angriff auf einen bekannten Login kann dessen Limit erreichen; andere Logins und
Quellen bleiben bis zur echten globalen Überlastgrenze erreichbar.

Abgelaufene Buckets dürfen mit `cleanup_login_buckets(connection, batch_size)` innerhalb einer
Operator-Transaktion entfernt werden (1–5000 Zeilen, `SKIP LOCKED`, idempotent). Der Runtime
werden dafür keine DELETE-Rechte erteilt. Regelmäßige Maintenance entfernt auch alte Buckets aus
früheren Versionen; die feste Partitionierung begrenzt neues Wachstum unabhängig davon.

## Credential-Auswahl und Logout

Authentication und Logout verwenden dieselbe zentrale Auswahl: Cookie-only oder Bearer-only
identifiziert jeweils genau eine Sitzung. Gleiche Cookie- und Bearer-Werte sind erlaubt und
behalten Cookie-CSRF/Origin-Prüfungen; unterschiedliche Werte oder malformed Authorization
liefern 401, ohne eine der Sitzungen zu widerrufen. Kein stiller Vorrang eines Transports.
Bearer-only Logout widerruft den Bearer-Session-Digest; Cookie-only Logout den Cookie-Digest.
Danach ist der Wert über beide Transporte ungültig. Bearer-only benötigt keine Browser-CSRF-
Header; Cookie-Requests weiterhin schon. Das Antwort-Cookie wird immer gelöscht.
Der explizite development/test-Token ist kein persistentes Credential: Logout widerruft ihn nicht
und öffnet dafür keine DB-Verbindung. Staging/Production akzeptiert ihn weiterhin niemals.

## Heartbeat und Retention

Jeder Request validiert weiterhin Sitzung und Berechtigung. `last_seen_at` wird nur nach
`AUTH_SESSION_HEARTBEAT_SECONDS` (Default 60) erneut geschrieben, mit atomarem SQL-Vergleich
gegen die alte Schwelle. Parallel eintreffende Requests erzeugen höchstens ein Update.
Absolute expiry bleibt unverändert; Idle-Aktivität wird konservativ in Intervallen erfasst.
Maintenance: `python -m app.auth.maintenance cleanup`, siehe [Betrieb](development.md#bereinigung).
Keine impliziten Deletes durch API-Requests und keine DELETE-Rechte für die Runtime.

## Research authorization

Independent accounts now have two explicit, independent grants:
`admin.auth_system_admin` permits Operations and Research;
`admin.auth_journalist` permits Research only. `AdminPrincipal` adds `journalist`.
`get_identity` retains the existing credential/CSRF/session checks,
`get_current_admin` remains the Operations dependency, and
`get_current_research_user` requires either grant. `/auth/session` permits either
grant; an active account with neither remains denied. Password verification and
login semantics are unchanged; inactive accounts cannot log in.

Migration `0015` adds only `admin.auth_journalist`, after verified head `0014`.
Deploy backend and frontend together, with API/workers stopped during the schema
and grant transition. Select the authorized migration target explicitly, migrate
using `ADMIN_MIGRATION_DATABASE_URL` and apply operator-provisioned grants before
starting the new runtime. Runtime startup never creates this table or repairs grants.
A missing table or SELECT grant prevents authentication and readiness; do not hot-reload
the new session query against the old schema.

```sql
GRANT SELECT ON admin.auth_journalist TO admin_user;
GRANT SELECT, INSERT, DELETE ON admin.auth_journalist TO admin_auth_operator;
```

The migrator owns the table. Runtime may not own it, inherit its owner, create in
admin, or modify grants. The existing boundary check rejects effective INSERT,
UPDATE, DELETE, TRUNCATE and TRIGGER privileges on all three auth identity tables.
Ansible's explicit operator/runtime contracts include the new table.

Run account commands from `backend/`, using only the separate operator connection:

```sh
uv run python -m app.auth.manage doctor
uv run python -m app.auth.manage create reporter-example --active --journalist
uv run python -m app.auth.manage grant-journalist existing-account-example
uv run python -m app.auth.manage revoke-journalist existing-account-example
```

Create prompts for the password without echoing it. `--journalist` is valid only
with create. Existing `grant`, `revoke` and `--system-admin` retain their meaning;
accounts can hold both grants. There is no public account/grant mutation endpoint.
As with existing operator changes, grant/revoke increments the credential version
and revokes prior sessions, including when the other grant remains. A fresh login
is required. Direct grant removal is also observed on the next authorization check.

After rollout, journalists use the existing `/login` and are directed to `/research`.
System administrators retain Operations as their default and can switch workspaces.
No actual account, password or deployed grant is created by the code change.

Research API GET routes: `/api/v1/research/search`, `/options`, `/export`,
`/events`, `/venues`, `/organizations` and the three `/:key` dossiers. All use
explicit public response models; original admin responses are not serialized into
Research. The source database remains read-only. See the
[workspace contract](../../frontend/docs/research-workspace.md) and
[source gaps](../../docs/research-backend-gaps.md).
