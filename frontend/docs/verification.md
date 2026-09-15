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
