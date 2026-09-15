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
| Space-Vererbung | [öffentliche Projektion](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/sql/get-events-projected.sql) verwendet COALESCE für Space; [Terminabfrage](https://github.com/sndcds/uranus/blob/733c54133362460353400eb96c60a0cdb9f8450a/sql/get-event-dates.sql) verwendet bedingte Vererbung nach Venue-Override | Regel benennt ausdrücklich die öffentliche COALESCE-Semantik in Meldung und metadata.inheritance; Quelltabellen bleiben Prüfbasis |
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
