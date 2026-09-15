# Activity-Stream

Die Activity-Seite zeigt **Neuanlagen**, keine rekonstruierten Statusänderungen oder fachlich
zusammengehörigen Bearbeitungsvorgänge. Backend und `activityPageSchema` bleiben unverändert.

## Darstellung

Eine gemeinsame weiße Listenfläche ersetzt einzelne große Karten. Pro Zeile: dezentes Typ-Icon,
kräftiger Name, Typ-Badge, Organisation, kompakte Aktionen, Status und Zeit. Auf Desktop stehen
Status und Zeit rechts; auf Mobile stehen sie unter dem Kontext. Technische UUID-Namen bzw.
fehlende Namen erhalten den ehrlichen Fallback „[Objektart] ohne Anzeigenamen“. Der vorhandene
Name bleibt als title zugänglich; der Objektschlüssel bleibt unverändert in den Action-/Markierungslinks.

Die zentrale Definition liegt in `app/utils/activity.ts`:

| Typ | Label | Lucide-Icon |
| --- | --- | --- |
| organization | Organisation | Building2 |
| venue | Ort | MapPin |
| space | Raum | DoorOpen |
| event | Veranstaltung | CalendarDays |
| event_date | Termin | Clock |
| user | Benutzer | User |
| partner_request | Partneranfrage | Handshake |
| team_membership | Teammitgliedschaft | Users |
| image | Bild | Image |

Bekannte Statuswerte aus `backend/app/repositories/activity.py` und den Source-Fixtures werden
übersetzt: released, draft, cancelled, pending, accepted, active, inactive, joined, invited.
Unbekannte Werte bleiben als Originaltext erhalten; bei NULL wird kein Status erfunden.

## Zeit und Seitengrenzen

Activity liefert keine `admin_timezone`. Die Darstellung verwendet deshalb wie die bestehende
`dateTime`-Utility **Europe/Berlin**, unabhängig von der Browser-Zeitzone. Eine abweichende
Backend-Konfiguration wird dadurch nicht automatisch übernommen. Datumsformatierer werden
wiederverwendet; die Gruppierung erhält die API-Reihenfolge innerhalb eines Tages.

„Heute“ und „Gestern“ beziehen sich auf den lokalen Kalendertag des API-`observed_at`;
der Abrufstand wird angezeigt. „Gestern“ wird kalendarisch ermittelt, auch bei Sommerzeitwechseln
mit 23 oder 25 Stunden. Ältere Gruppen erhalten ein ausgeschriebenes Datum. Vollständiges Datum
und Zeitzone sind an jedem `<time>` über title und zugängliche Beschriftung verfügbar.

Bei `timestamp_state=unknown` gibt es **keine Tagesgruppen**. Der Hinweis zur reinen
Objektschlüsselreihenfolge bleibt erhalten. NULL-Zeitstempel erscheinen als „Ohne Zeitstempel“;
auch eine unerwartete NULL-Zeile in einer known-Antwort wird keinem erfundenen Tag zugeordnet.

Typzahlen und Gruppenanzahlen beziehen sich ausdrücklich nur auf die sichtbaren `items`.
`pagination.total` steht separat als Gesamtzahl der gefilterten Ergebnismenge. Eine Tagesgruppe
kann über mehrere Seiten verteilt sein; es werden keine seitenübergreifenden Zahlen abgeleitet.

## Bedienung und Accessibility

- Deutsche Objektart-Auswahl, Zeitraum, Organisation-UUID, explizites Anwenden und Filter-Reset.
- Filterwerte folgen der URL auch bei Zurück/Weiter im Browser; unknown wird korrekt vorausgewählt.
- Pagination erhält bestehende URL-Parameter und zeigt „Seite X von Y“; an Grenzen sind Buttons
  wirklich disabled. Eine leere Ergebnismenge zeigt keine fiktive Seitenanzahl.
- RequestState, Retry, Auth-Verlust und Schutz vor verspäteten Antworten bleiben erhalten.
- Semantische `ul/li`, Gruppenüberschriften h3 und Datensatztitel h4 (ohne Gruppen h3).
- Icons sind aria-hidden; Typen und Status tragen Text. Links nennen ihren Zieldatensatz.
  Vorhandene sichtbare Fokusumrandungen bleiben aktiv.

## Visueller Vergleich

Ausschließlich synthetische Daten aus `tests/fixtures/activity.ts`, jeweils dieselben 20 Zeilen
bei 80 Gesamttreffern. Viewports: Desktop 1440 × 1100, Mobile 390 × 844. Auth- und Activity-Antworten
wurden für die Screenshots kontrolliert ersetzt; keine Live-Daten oder Credentials.

| | Vorher | Nachher |
| --- | --- | --- |
| Desktop | [Vorher](screenshots/activity-before-desktop.png) | [Nachher](screenshots/activity-after-desktop.png) |
| Mobile | [Vorher](screenshots/activity-before-mobile.png) | [Nachher](screenshots/activity-after-mobile.png) |

Die Desktop-Ansichten zeigen bei gleicher Fenstergröße sechs statt drei vollständig sichtbare
Datensätze. Ergänzend: [Mobile-Stream nach Scrollen](screenshots/activity-after-mobile-stream.png).

Tests: `tests/unit/activity.test.ts` prüft Labels, Links, Status-/Namens-Fallbacks, Kalendergrenzen,
Sommerzeit, Gruppierung und Seitenzahlen. `tests/e2e/activity-stream.spec.ts` prüft den echten
Production-/Development-Client mit kontrollierten API-Antworten, einschließlich Filter, History,
Pagination, Leerzustand, Ladezustand, Fehler und Retry.
