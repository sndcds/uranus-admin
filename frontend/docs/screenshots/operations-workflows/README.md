# Operations Workflows v2.1 — synthetischer Review

**Zwischenstand vom 23.09.2026, 21:33–21:34 Uhr (Europe/Berlin).** Diese vorhandenen
Aufnahmen stammen aus dem früheren synthetischen Reviewlauf. Sie zeigen noch nicht die
abschließende Findings-Spaltenaufteilung, die deutschen Regelbezeichnungen, Live-SQL,
die gemeinsame Kopierkomponente oder die SQL-Zeilennummernkorrektur. Eine aktuelle
Screenshot-Matrix und die vollständige Validierung stehen aus: weitere lokale Tests
wurden auf ausdrücklichen Wunsch wegen Rechnerauslastung gestoppt.
`marks-scoped-desktop.png` zeigt nur den Datensatzkontext während des Ladevorgangs;
die Aufnahme mit vollständig geladener Liste muss ebenfalls erneuert werden.

Die Aufnahmen verwenden ausschließlich `tests/fixtures/operations-workflows.ts` und
lokal abgefangene Bildantworten. Namen, Zahlen, Bilder und Zeitpunkte sind synthetisch;
die Screenshots belegen keinen produktiven Datenstand.

| Ansicht                          | Desktop (1440 × 1000)               | Mobile (390 × 844)               |
| -------------------------------- | ----------------------------------- | -------------------------------- |
| Inbox                            | [Desktop](inbox-desktop.png)        | [Mobile](inbox-mobile.png)       |
| Befunde                          | [Desktop](findings-desktop.png)     | [Mobile](findings-mobile.png)    |
| Markierungen                     | [Desktop](marks-desktop.png)        | –                                |
| Markierungen im Datensatzkontext | [Desktop](marks-scoped-desktop.png) | –                                |
| Markierungsdetail                | [Desktop](mark-detail-desktop.png)  | [Mobile](mark-detail-mobile.png) |

Zusätzlich prüft die Browsermatrix 1024 × 768 und 360 × 800. Die Testartefakte enthalten
auch diese Aufnahmen. Die Matrix läuft einmal im Desktop-Projekt mit explizit gesetzten
Viewportgrößen; vier identische Wiederholungen im Mobile-Projekt werden übersprungen.

## Aktueller implementierter Funktionsumfang (teilweise neuer als die Aufnahmen)

- Inbox: globale Counts mit URL-Shortcuts, kompakte Filter, priorisierte Aufgaben,
  Zuständigkeit/Fälligkeit, getrennte fachliche und operative Wiedervorlage, Technik.
- Befunde: Tabelle mit Priorität und Status, ausdrücklich seitenlokale Severity-Zahlen,
  sichere Bilder/Typ-Platzhalter und direkte Aktionen „Im Admin ansehen“/„SQL Editor“.
  Befund-Detailmodal und Markierungsaktion wurden auf Wunsch entfernt. Daher gibt es
  keine Aufnahme `findings-detail-desktop.png`. SQL-Aktion und SQL-Hashlinks bleiben erhalten.
- Markierungen: kompakte manuelle Arbeitsliste, geschlossene Erstellung im Datensatzkontext,
  getrennte Bearbeitung und unveränderlicher Verlauf, belegte technische Metadaten.
- Vorschaubilder: gemeinsame Bildzuordnung, keine Detailrequests pro Zeile; defekte oder
  fehlende Bilder erhalten einen Typ-Platzhalter. Die Bildvorschau öffnet kein Modal.

## Reproduktion und Prüfung

Aus `frontend/` nach Installation und erfolgreichem Build:

```sh
pnpm test:e2e tests/e2e/operations-workflows.spec.ts --output=/tmp/operations-workflows-review
TEST_PRODUCTION=1 pnpm test:e2e tests/e2e/operations-workflows.spec.ts --output=/tmp/operations-workflows-production
```

Die Dateien werden im jeweiligen Testausgabeverzeichnis erzeugt. Für Änderungen an
Referenzbildern passende Desktop-/Mobile-Dateien bewusst in dieses Verzeichnis kopieren.

Die Regressionen prüfen alle vier Viewports auf Seitenüberlauf, direkte zugängliche
Aktionen, kompakte Desktop-Linkhöhe, globale Inbox-Shortcuts, URL-/History-/Pagination-
Semantik, Mark-Konflikte mit erhaltenem Entwurf, lange Notizen, echte Technikwerte sowie
Bilddarstellung in Live-/Persisted-Modus unter der bestehenden Production-CSP.
Ergänzende Unit-/E2E-Suites decken Formvalidierung, Erledigen/Wiederöffnen, SQL-Dialogfokus,
Geo Scope, Auth-Verlust und den Erhalt letzter Antworten nur bei derselben Query ab.

Sichtung der vorhandenen Aufnahmen: Inbox, Markierungsliste und Markierungsdetail sind
als Zwischenstand dokumentiert. Der endgültige responsive Review einschließlich
Seitenüberlauf für alle vier Viewports ist noch offen. Die Dateien sind keine Aussage
über einen vollständig grünen Testlauf oder über das finale Findings-Layout.
