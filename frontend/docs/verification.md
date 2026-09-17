# Verifikation von PR #14

Stand: 2026-09-15, Branch `feat/admin-review-findings`, Node 22.22.3, pnpm 12.3.4.

| Prüfung | Ergebnis |
| --- | --- |
| pnpm install --frozen-lockfile | erfolgreich, Lockfile unverändert |
| pnpm lint | erfolgreich |
| pnpm typecheck | erfolgreich |
| pnpm test | 59 Tests bestanden |
| pnpm build | erfolgreich |
| TEST_PRODUCTION=1 pnpm test:e2e | 20 Tests bestanden, Desktop/Mobil, 13,8 Sekunden |
| pnpm test:e2e | 20 Tests bestanden, Desktop/Mobil, 47,4 Sekunden |

Der neue Browserfall prüft, dass Navigation und Aktualisierung `mode=persisted` senden und
`mode=live` erst nach ausdrücklicher Auswahl verwendet wird. Zusätzliche Unit-Tests decken den
Standardmodus, ungültige UUID-Detailpfade, Header-Allowlist und `credentials: omit` ab.
Bestehende Navigation, Pagination, Zugangs-/Fehlerzustände, unbekannte Zeitstempel, Reviews,
Markierungen, Notizen, Abschluss/Wiederöffnung und die reale Nitro-Grenze bleiben geprüft.

Playwright startet ausschließlich lokale Testserver; Serverstarts sind in der Sandbox blockiert
und wurden mit Freigabe außerhalb ausgeführt. Browserdaten sind synthetisch. Die Tests ersetzen
keine produktive Uranus-Autorisierung oder Lastmessung. Die bestehenden NO_COLOR/FORCE_COLOR-
Warnungen und Build-Profiling-Hinweise sind keine Testfehler.

Backend: 168 Tests einschließlich PostgreSQL/PostGIS, SCRAM-Login, Migrationen und Runtime-Rechten
bestanden, keine übersprungen. Details im [Review-Bericht](../../backend/docs/pr14-review-verification.md).
GitHub-Ergebnisse stehen bei den [PR-Prüfungen](https://github.com/sndcds/uranus-admin/pull/14/checks).

## Logoqualität — 2026-09-17

Basis: frisch abgerufenes `main` bei `8439992`; Umsetzung auf `feat/logo-quality`
im separaten Worktree, um zeitgleiche Auth-Änderungen im ursprünglichen Arbeitsverzeichnis
zu erhalten. Backend-Regeln, Dashboard-Zähler und UI verwenden die bestehenden Verträge.

| Prüfung | Ergebnis |
| --- | --- |
| `uv run ruff check .` | erfolgreich |
| `uv run ruff format --check .` | erfolgreich |
| `uv run mypy` | erfolgreich, 81 Quelldateien |
| `uv run pytest` | 469 bestanden, keine übersprungen; separate lokale PostgreSQL/PostGIS-Testdatenbank |
| `pnpm lint` | erfolgreich |
| `pnpm typecheck` | erfolgreich |
| `pnpm test` | 179 bestanden |
| `pnpm build` | erfolgreich |
| `pnpm test:e2e --workers=2` | zunächst 81 bestanden, 7 fehlgeschlagen, 4 Production-spezifische Tests übersprungen |
| `pnpm test:e2e --last-failed --workers=2 --retries=1` | alle 7 zuvor fehlgeschlagenen Tests bestanden, ohne weitere Wiederholung |
| `TEST_PRODUCTION=1 pnpm test:e2e --workers=4 --fully-parallel` | 92 bestanden, keine übersprungen, 3,7 Minuten |

Die sieben anfänglichen Dev-Fehler betrafen bestehende Activity-/Layout-Fälle:
unter anderem ein fehlgeschlagener dynamischer Nuxt-Import und Gesamttimeouts bei
Rundgängen durch 19 Seiten. Für die gezielte Wiederholung wurde deren lokales
Layout-Zeitlimit vorübergehend von 120 auf 240 Sekunden gesetzt. Die einzelnen
Layout-Wiederholungen dauerten anschließend 1,1–1,8 Minuten. Vor dem Production-Lauf
wurde das ursprüngliche Limit wiederhergestellt.

Alle acht neuen Logo-E2E-Fälle bestanden bereits im ersten Dev-Lauf und erneut im
Production-Build: drei Drilldowns plus Loading/Error/Retry/Empty-State, jeweils auf
Desktop und Mobilgeräten. Sie prüfen Regel-/Entity-Filter, Counts, Warning/Info,
Entity-Beschriftung und kanonische Detail-Links. Screenshots der Logo-Gruppe wurden
auf Desktop und Mobilgeräten visuell geprüft.

Die Standardports waren durch eine andere Arbeit belegt; beide Läufe verwendeten
vorübergehend 3139/31939 statt 3100/31902. Die Portanpassungen und das erhöhte
Layout-Testlimit sind vollständig zurückgenommen. Der Production-Lauf startete
nur den lokalen Build mit synthetischen Fixtures. Die wegwerfbare Backend-Testdatenbank
wurde anschließend entfernt. Es gab keine Bereitstellung und keine produktiven Source-Writes.
