# Geprüfter Bestandskatalog für die SQL-Console

Contract v5 / Function Policy v3 ergänzt den am 20. September 2026 ausschließlich
lesend erfassten Bestand. Grundlage ist der frisch abgerufene `main` bei
`6e44b2c9d32da84c750b468f9fc60da1d98fb196`, einschließlich des inzwischen
gemergten Audit-PRs #78. Diese Dokumentation beschreibt den überprüfbaren
Provisionierungsentwurf, keinen erfolgten produktiven Apply. Die bestehenden Deployment-Freigaben gelten weiter.

## Erhalt bestehender Rechte

`database_temp_roles` enthält weiterhin die vier erforderlichen App-Loginrollen.
`additional_database_temp_roles` enthält 14 konkret erfasste weitere Verbraucher.
Zusätzliche Rollen sind optional: Der Validator berücksichtigt sie nur, wenn sie
bereits existieren, und erstellt sie niemals. Eine vorhandene Rolle ohne LOGIN,
ein unbekannter Verbraucher, Grant Options oder ein Membership-/SET-ROLE-Pfad
blockiert weiterhin. Ist PUBLIC TEMP bereits entzogen, werden fehlende Rechte
nicht neu erteilt (`missing_preserved_temp`).

EXECUTE verwendet unabhängig davon `execute_roles` und
`additional_execute_roles`. Letztere Liste enthält zusätzlich `oklab`: Dessen eigene
Datenbank-TEMP-ACL wird separat erhalten; bei Funktionen anderer Eigentümer bezieht
die Rolle EXECUTE bislang über PUBLIC. Die Listen sind keine Erlaubnis zu neuen
Rechten: Nur für eine exakt geprüfte Signatur mit aufgezeichnetem PUBLIC EXECUTE
darf der Übergang erfolgen. Vor dem PUBLIC-Entzug erhalten die vorhandenen
Verbraucher explizite Grants in derselben Transaktion. Nach manuellem Entzug von
PUBLIC werden fehlende Erhaltungsgrants nicht wiederhergestellt.

PostgreSQL addiert direkte, geerbte und PUBLIC-Rechte; ein REVOKE nur bei den
Console-Rollen entfernt daher kein PUBLIC-Recht.
Siehe [GRANT](https://www.postgresql.org/docs/16/sql-grant.html).

## Vier zusätzliche Extensions

Nur im PostgreSQL-16-/PostGIS-3.4.2-Snapshot werden folgende optionale Extensions
akzeptiert; reproduziert und geprüft wurde er auf PostgreSQL 16.15. Keine Installation,
Aktualisierung oder Entfernung von Extensions; andere Katalogstände bleiben blockiert.

| Extension | Version | Funktionen | Vollständiger Katalog-SHA256                                       |
| --------- | ------- | ---------- | ------------------------------------------------------------------ |
| hstore    | 1.8     | 60         | `2316812ebb7444b4a1ed24e16275239c0116e1c3cf429d4aeb94575d0ba6228d` |
| pg_trgm   | 1.6     | 31         | `c3575538cb70ecf7ec3c57bbea2867c94fbfedf1a677fb6bbfed94db47af3d1c` |
| pgcrypto  | 1.3     | 36         | `604e37402ca09551c05b3e2e2978db82b39b2cb65c9ed0c109fe6a235b8234f3` |
| unaccent  | 1.1     | 4          | `498de0f29eefb59526a777f7b3c785e286ae79dc4a2e8748c3a852a017703aa6` |

Die Kataloge wurden in einer separaten Datenbank aus den PostgreSQL-Paketen des
[gepinnten Ubuntu-Testbuilds](../../ansible/tests/images/pg16-postgis342/README.md)
mit `CREATE EXTENSION ... WITH SCHEMA public` reproduziert und mit den Audit-Hashes
verglichen. Der Vertrag enthält ausschließlich Hashes, Signaturen und ACL-Metadaten.
Jede der 131 Funktionen ist für direkte Console-Aufrufe eingeschränkt, unabhängig
von ihrer Volatility. Schema, C-Sprache, passende `$libdir/<extension>`-Bibliothek,
Definition, Extension-Zugehörigkeit und privilegierter Funktionseigentümer müssen
übereinstimmen. Funktionsrechte der Anwendungen bleiben erhalten.

Ein Funktions-REVOKE schaltet nicht jede implizite Typoperation ab. Insbesondere
die Ein-/Ausgabe des nativen hstore-Typs kann weiterhin erfolgen. Die akzeptierten
Implementierungen verarbeiten Werte; daraus folgt keine Schreibberechtigung auf
Quelltabellen. Der Integrationstest prüft diesen Unterschied ausdrücklich. Neue
oder veränderte Implementierungen bleiben durch den vollständigen Katalog geblockt.
Fachliche Grundlagen: [hstore](https://www.postgresql.org/docs/16/hstore.html),
[pg_trgm](https://www.postgresql.org/docs/16/pgtrgm.html),
[pgcrypto](https://www.postgresql.org/docs/16/pgcrypto.html),
[unaccent](https://www.postgresql.org/docs/16/unaccent.html).

## Zwölf eigene Funktionen

Die separat genehmigten Produktionsdefinitionen wurden lokal mit Modus 0600
gesichert und statisch geprüft. Sie werden weder ausgeführt noch ins Repository
aufgenommen. Die zwölf Definitions-Hashes stimmen mit dem ursprünglichen Audit
überein. Fünf skalare Helfer und sieben Triggerfunktionen verwenden SQL/PLpgSQL,
SECURITY INVOKER und keinen festgelegten funktionslokalen search_path. Ein Trigger
enthält ein UPDATE auf `uranus.event`; weitere Trigger verändern NEW oder lesen
Quelltabellen. Kein dynamisches EXECUTE wurde gefunden. Mehrere Helferaufrufe sind
unqualifiziert; die beiden `normalize_german`-Implementierungen unterscheiden sich.

Alle zwölf Einträge unter `custom_functions` sind für **beide** Console-Rollen
eingeschränkt und nur auf PostgreSQL 16.15 / PostGIS 3.4.2 geprüft. Eine vorhandene
Funktion muss Signatur, Hash, Sprache, Art,
Volatility, Sicherheitsattribute und die unten beschriebene Eigentümerregel
erfüllen. Fehlende Funktionen werden nicht angelegt. Unbekannte Funktionen bleiben
Blocker, auch bei privater ACL. Die Console-Views benötigen keinen dieser Helfer.

Zusätzlich prüft der Validator Rückverweise in `pg_depend`: Trigger und die anderen
ebenfalls gesperrten, geprüften Funktionen sind erlaubt; Views, Operatoren, Casts,
Typen und sonstige abhängige Objekte führen zu
`unreviewed_custom_function_dependency`. Damit wird ein bekannter Funktions-Hash
nicht als allgemeine Freigabe indirekter Aufrufpfade behandelt. Produktive
Triggerbindungen werden nicht verändert. Der feste Console-search_path bleibt
`pg_catalog, uranus_console`.

## Konkrete Eigentümerregeln

Die bisherige Superuser-/Extension-Eigentümerregel bleibt der Normalfall. Nur im
3.4.2-Snapshot sind zwei beobachtete Abweichungen eingetragen:

- Die drei unveränderten, vollständig fingerprintgeprüften PostGIS-Metadatenobjekte
  dürfen `oklab` gehören; ihr vorhandenes SELECT bleibt bestehen.
- Die pgcrypto-Extension darf `oklab` gehören. Ihre Funktionen müssen weiterhin
  privilegierten Installationsrollen gehören und exakt dem geprüften C-Katalog
  entsprechen. Die Extension-Eigentümerschaft erlaubt keine selbst geschriebenen
  oder von `oklab` besessenen Ersatzfunktionen.

Auch die zwölf eigenen Funktionen müssen `oklab` gehören. Für diese konkreten
Objekte bedeutet `oklab`: Eigentümer der aktuellen Datenbank, LOGIN, CREATEDB,
INHERIT; kein SUPERUSER, CREATEROLE, REPLICATION oder BYPASSRLS und keinerlei
Rollenmitgliedschaft in irgendeiner Richtung. Der Quellen-Eigentümer ist bereits
Teil der Vertrauensgrenze der gelesenen Uranus-Daten. Das ist keine pauschale
Ausnahme für beliebige Datenbankeigentümer. Eigentümer und Rollenattribute werden
niemals automatisch verändert. Die Prüfung bindet den aktuellen Zustand; ein
späterer Eigentümer-/Definitionswechsel benötigt erneut Preflight und Review.

## Validierung und Betrieb

Die Tests verwenden ausschließlich wegwerfbare Datenbanken und synthetische
Funktionskörper. Zwei lokale Fixture-Hashes werden in einer Vertragskopie ersetzt;
das ist kein zusätzlicher Nachweis für die fachliche Produktionsimplementierung.
Der echte Definitionsreview bleibt davon getrennt.

Abgedeckt werden vollständiger Rechteerhalt, verbotene Console-Aufrufe, getrennte
TEMP-/EXECUTE-Listen, Typ-I/O, zweiter Apply ohne Änderung, unbekannte Verbraucher,
Versions-/Definitions-/Owner-Drift, Memberships, indirekte View-/Operatorpfade,
manuelle Härtung ohne erneute Rechtevergabe und Rollback nach spätem Fehler.
Die übrigen beiden CI-Stacks prüfen weiterhin ihren bisherigen Vertrag und lehnen
die nicht für sie geprüften zusätzlichen Extension-Kataloge ab.

Nach den lokalen Tests kann der separat autorisierte Katalogaudit einen neuen
lesenden Plan erzeugen. Bei unverändertem Bestand plant er den PUBLIC-Entzug für
96 Core-, 95 PostGIS-, 131 Contrib- und zwölf eigene Signaturen sowie den TEMP-
Übergang. Erst ein geprüfter aktueller Dry Run und die bestehenden ausdrücklichen
Apply-Freigaben erlauben produktive Änderungen. Fehler vor Commit rollen alle
ACL- und Console-Änderungen zusammen zurück.

Der separat genehmigte lesende Produktionsaudit am 20. September 2026 um 20:56 UTC
ergab mit diesem Vertrag **null Blocker** und 733 geplante Aktionen. Funktions-ACLs,
Rollen, Memberships, Extensions und PostGIS-Metadaten waren gegenüber dem vorherigen
Export unverändert. Das bestätigt den Katalogplan zu diesem Zeitpunkt, nicht einen
vollständigen Deployment-Dry-Run oder eine erfolgte Provisionierung.
