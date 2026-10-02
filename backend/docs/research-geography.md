# Geographic Research

The coordinated [planner PR #15](https://github.com/sndcds/uranus-research-planner/pull/15)
introduces `research-query-plan-v6` / `research-planner-v11` and adds required
nullable `place_query` and `location_relation: none | nearby` to the frozen v5 analytical
contract. The planner remains lookup-free. Admin and planner JSON Schemas are identical;
the reviewed DE/EN/DA fixtures test transport and interpretation expectations with mocked
model output, not deployed model accuracy.

- Streets, squares and local places use `place_query` (Bachstraße Flensburg, Nordermarkt).
- Cities/administrative regions use `area_query`; known event venues use `venue_query`.
- “Wo finden [heute] Veranstaltungen statt?” lists events and their venue/address;
  `wo`, `where` and `hvor` alone never require the user's location.
- “Hier”, “bei mir” and “in meiner Nähe” use `location_relation=nearby` and
  `clarification=needs_location`. The planner receives no coordinates. Admin satisfies
  that requirement from validated request context and returns records, or asks for location.
  The response retains the original planner envelope for inspection; the execution result
  is authoritative about whether clarification remains necessary.

## Activation and transport

Deploy planner `/v6/plan` **before** configuring `RESEARCH_GEOCODER_API_KEY` in Admin.
A configured geocoder key selects v6 for `/research/query`; without it existing v3/v5
selection remains unchanged. There is no silent downgrade of geographic requests.
The separate `/research/plan` legacy endpoint stays frozen.

```dotenv
RESEARCH_GEOCODER_URL=http://127.0.0.1:6337
RESEARCH_GEOCODER_API_KEY=
RESEARCH_GEOCODER_TIMEOUT_SECONDS=5
```

Provision the geocoder's Bearer service key in Admin's protected server environment.
HTTP requires a numeric loopback address; HTTPS may use a trusted configured host.
Origins cannot contain a path, credentials, query or fragment. If Admin and the AI host
are different machines, operators must provide the loopback tunnel before activation;
this change neither deploys nor changes live services or SSH access.

`ResearchGeocoderClient` calls only the internal service: `/search`, `/reverse`, `/lookup`
and `/ready`. No Research place request goes directly to Nominatim. The geocoder API's
bounding-box order is **south, west, north, east**, not GeoJSON order. Responses are
strictly validated and limited to 256 KiB. The total deadline defaults to five seconds;
there are no redirects, retries, environment proxies or forwarded browser cookies/keys.
404 becomes no match; provider errors, invalid responses and timeouts become the safe
503 `geocoder_unavailable`. Existing administrative boundary import tools are unaffected.

## Resolution and execution

Exactly one candidate may resolve. Multiple results require clarification; provider order
never picks a winner. A result without usable address/geometry fails closed. Browser
requests cannot submit OSM IDs, SQL, radii, bounding boxes or upstream URLs.

Selection priority for named places:

1. A street/road with `address.road` and `address.city`, or a complete numbered address:
   exact case-insensitive, whitespace-normalized venue street and city; house number when
   supplied. This deliberately works with authoritative source addresses even without a point.
2. Non-point places with a non-degenerate bounding box: PostGIS `ST_Covers` with an indexed
   bounding-box prefilter. Never infer a polygon that the service did not supply.
3. A point or remaining coordinate-bearing result: PostGIS geography `ST_DWithin`, **250 m**.

An explicit user-coordinate context always uses **500 m around those coordinates**.
Reverse-geocoded street/city/bbox metadata never replaces the user's position or widens
that radius. Missing, empty, invalid or out-of-range source points cannot satisfy either
geometry branch. Unknown event locations never count as geographic matches. The same
predicate applies to effective occurrence venues, complete semantic eligibility and final
rehydration. Date/time, publication, taxonomy, venue and organization constraints intersect
with the place selection. Zero matches remain a successful empty records result.

## Browser context and privacy

`POST /research/query` accepts optional `location_context` with a finite lat/lon pair,
optional nonblank display name (160 characters), and source
`browser_geolocation | nominatim_reverse | manual`. Either coordinates or a name are required.
The source and display name are untrusted hints, never proof of identity or permission.
Name-only manual context is resolved through `/search`.

The UI requests browser position only after “Standort freigeben”. Denial exposes manual
entry. It resubmits the original question with context in the POST body, reuses that context
for subsequent questions in the current component, and clears it on auth changes/unmount.
Coordinates never enter links, local/session storage or telemetry. A canonical reverse label
returned by Admin is reused; coordinates with an existing display name do not need another
reverse call because execution already has sufficient validated coordinates. Unrelated
questions do not implicitly acquire the location filter.

Queries containing `place_query`, nearby requests, and requests carrying any location context
are excluded from successful-question learning. Diagnostics contain durations/counts only,
not coordinates, addresses or place text. No new logs or persistence of location data exist.

## Validation

`test_research_geocoder.py` and `test_research_geography.py` cover transport/auth/config,
closed input, ambiguity, no match, safe errors, the four main question regressions, manual
context and learning exclusion. PostGIS tests use the existing disposable database fixture
in CI (no Docker run required locally). Frontend tests cover click-only geolocation, denial,
resubmission, context reuse, auth invalidation, body-only coordinates and proxy validation.
No migration, grants or Uranus writes are introduced.
