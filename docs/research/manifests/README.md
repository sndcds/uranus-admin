# Reviewed administrative import inventory

Reviewed on **2026-10-04**. See [the operator guide](../persistent-administrative-areas.md)
for plan/apply, persistence constraints and restart semantics. These manifests
contain exact identities, not runtime discovery instructions.

## German states

All 16 state relations were verified. Berlin and Hamburg are protected municipality
identities and have no executable state manifests. The 14 other manifests have
`level=state`, `country_codes=["DE"]`, reviewed raw OSM level 4 and `complete=false`.
Bremen has a distinct state relation; Bremen city and Bremerhaven are excluded.

| Subdivision | Reviewed name          | Relation | Manifest / disposition                       |
| ----------- | ---------------------- | -------- | -------------------------------------------- |
| DE-BB       | Brandenburg            | 62504    | [de/states/DE-BB.json](de/states/DE-BB.json) |
| DE-BE       | Berlin                 | 62422    | **Excluded: municipality identity**          |
| DE-BW       | Baden-Württemberg      | 62611    | [de/states/DE-BW.json](de/states/DE-BW.json) |
| DE-BY       | Bayern                 | 2145268  | [de/states/DE-BY.json](de/states/DE-BY.json) |
| DE-HB       | Bremen                 | 62718    | [de/states/DE-HB.json](de/states/DE-HB.json) |
| DE-HE       | Hessen                 | 62650    | [de/states/DE-HE.json](de/states/DE-HE.json) |
| DE-HH       | Hamburg                | 62782    | **Excluded: municipality identity**          |
| DE-MV       | Mecklenburg-Vorpommern | 28322    | [de/states/DE-MV.json](de/states/DE-MV.json) |
| DE-NI       | Niedersachsen          | 62771    | [de/states/DE-NI.json](de/states/DE-NI.json) |
| DE-NW       | Nordrhein-Westfalen    | 62761    | [de/states/DE-NW.json](de/states/DE-NW.json) |
| DE-RP       | Rheinland-Pfalz        | 62341    | [de/states/DE-RP.json](de/states/DE-RP.json) |
| DE-SH       | Schleswig-Holstein     | 51529    | [de/states/DE-SH.json](de/states/DE-SH.json) |
| DE-SL       | Saarland               | 62372    | [de/states/DE-SL.json](de/states/DE-SL.json) |
| DE-SN       | Sachsen                | 62467    | [de/states/DE-SN.json](de/states/DE-SN.json) |
| DE-ST       | Sachsen-Anhalt         | 62607    | [de/states/DE-ST.json](de/states/DE-ST.json) |
| DE-TH       | Thüringen              | 62366    | [de/states/DE-TH.json](de/states/DE-TH.json) |

## German rural districts

Every one of the 294 members of the
[Deutscher Landkreistag inventory](https://www.landkreistag.de/der-verband/landesverbaende/mittelbare-mitglieder)
is represented exactly once, in the containing Bundesland. `complete=true` means
complete **rural-district** inventory of that state, with municipality-role cities
excluded. This includes Region Hannover, StädteRegion Aachen and Regionalverband
Saarbrücken. It does not mean all OSM admin-level-6 objects or full land coverage.
Berlin, Hamburg and Bremen have no rural districts and no district manifests.

| Subdivision | Rural districts | Manifest                                           |
| ----------- | --------------: | -------------------------------------------------- |
| DE-BB       |              14 | [de/districts/DE-BB.json](de/districts/DE-BB.json) |
| DE-BW       |              35 | [de/districts/DE-BW.json](de/districts/DE-BW.json) |
| DE-BY       |              71 | [de/districts/DE-BY.json](de/districts/DE-BY.json) |
| DE-HE       |              21 | [de/districts/DE-HE.json](de/districts/DE-HE.json) |
| DE-MV       |               6 | [de/districts/DE-MV.json](de/districts/DE-MV.json) |
| DE-NI       |              37 | [de/districts/DE-NI.json](de/districts/DE-NI.json) |
| DE-NW       |              31 | [de/districts/DE-NW.json](de/districts/DE-NW.json) |
| DE-RP       |              24 | [de/districts/DE-RP.json](de/districts/DE-RP.json) |
| DE-SH       |              11 | [de/districts/DE-SH.json](de/districts/DE-SH.json) |
| DE-SL       |               6 | [de/districts/DE-SL.json](de/districts/DE-SL.json) |
| DE-SN       |              10 | [de/districts/DE-SN.json](de/districts/DE-SN.json) |
| DE-ST       |              11 | [de/districts/DE-ST.json](de/districts/DE-ST.json) |
| DE-TH       |              17 | [de/districts/DE-TH.json](de/districts/DE-TH.json) |

## Danish regions

These five entries use `level=region`, `country_codes=["DK"]`, reviewed raw
OSM level 4 and `complete=false`. Raw level 4 does not make them German-style
states. Municipalities continue through their existing import workflow.

| Subdivision | Name               | Relation | Manifest                                       |
| ----------- | ------------------ | -------- | ---------------------------------------------- |
| DK-81       | Region Nordjylland | 1319936  | [dk/regions/DK-81.json](dk/regions/DK-81.json) |
| DK-82       | Region Midtjylland | 1319935  | [dk/regions/DK-82.json](dk/regions/DK-82.json) |
| DK-83       | Region Syddanmark  | 1319978  | [dk/regions/DK-83.json](dk/regions/DK-83.json) |
| DK-84       | Region Hovedstaden | 1320608  | [dk/regions/DK-84.json](dk/regions/DK-84.json) |
| DK-85       | Region Sjælland    | 1320370  | [dk/regions/DK-85.json](dk/regions/DK-85.json) |

## Review evidence and exclusions

[reviewed-inventory.csv](reviewed-inventory.csv) records 315 reviewed identities:
16 states, 294 districts and 5 regions. It includes names, exact relation IDs,
versions, raw admin levels, official codes, DLT inventory names and versioned OSM
API URLs. There are 313 importable identities across 32 executable manifests.
The CSV is authoring evidence; the importer does not read it or derive roles from it.

[excluded-municipalities.csv](excluded-municipalities.csv) records all 107 German
`CITY_EXCEPTIONS` identities from the existing municipality importer. None occurs
in an executable nonmunicipal manifest. This includes Hanau and the protected
Berlin/Hamburg state relations. No Danish municipality identity is reused: each
region was verified by its exact ISO3166-2 tag and raw level 4 against the OSM API
and the [OSM Denmark administrative inventory](https://wiki.openstreetmap.org/wiki/Denmark/Da:Administrative_boundaries).
The Geocoder's municipality-role exclusion still applies at import time.

Authoring procedure (not run by plan/apply):

1. Read Germany's [country relation R51477](https://www.openstreetmap.org/relation/51477)
   and its 16 `subarea` state identities. Verify each state's exact ISO3166-2 tag,
   level 4 and administrative boundary tags in the primary OSM relation API.
   Use the administrative Schleswig-Holstein R51529 and Mecklenburg-Vorpommern
   R28322 relations, not alternate landmass relations from older wiki tables.
2. Retrieve OSM relation metadata through Overpass using the two explicit German
   official-key tags and raw admin level 6. The snapshot timestamp was
   `2026-10-04T07:11:01Z`. This is candidate authoring input,
   never runtime authority. The query shape is:

   ```overpass
   [out:json][timeout:40];
   (
     rel["de:amtlicher_gemeindeschluessel"]["admin_level"="6"];
     rel["de:regionalschluessel"]["admin_level"="6"];
   );
   out tags;
   ```

3. Require `type=boundary`, `boundary=administrative` and a five-digit district
   key; derive the containing state from its official key prefix. Exclude the
   existing municipality exceptions, then review all remaining identities against
   the DLT's state-specific membership list. Explicitly review label differences
   such as bilingual Bautzen/Spree-Neiße and abbreviated Bavarian names. Keep both
   names in the evidence CSV. This matched all 294 intended districts.
   Greiz R62445 has an AGS tag but no regional-key tag; it is included using its
   verified `de:amtlicher_gemeindeschluessel=16076`.
4. Exclude the nonadministrative `type=land_area` alternatives R62583 (Steinburg),
   R69951 (Pinneberg) and R5409700 (Leer). The selected administrative relations are
   R27016, R62408 and R62567 respectively. No duplicated landmass identity is used.
5. Fetch all selected district and excluded city relations directly from the
   primary OSM API in sequential batches, retaining reviewed versions and tags.
   Read the five Danish IDs from the OSM wiki inventory and confirm each exact
   relation's ISO subdivision, boundary tags and level in that API.

All requested rural-district and Danish region identities were verified; none was
omitted as unverifiable. Berlin and Hamburg are verified but intentionally excluded
from state persistence because of the storage model. Checked-in output is explicit,
deterministic and reviewable. Public OSM access is authoring-only; apply uses the
configured private Research Geocoder and still requires valid current boundaries.

OSM-derived identity metadata © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright). DLT membership
is used to cross-check the factual inventory, not to import office-holder details.
