# Research source boundaries and follow-ups

Baseline: `dev` at `8b63e011c71de0b8ef377965005a537d58710f69` (Operations PR #129).
Only `sndcds/uranus-admin` was inspected and changed. No live source catalog or
other repository was accessed. Checked-in source contracts, existing projections
and tests provide the implementation evidence; synthetic fixtures are not proof
of a deployed Uranus schema.

| Desired feature                                            | Required data                                                | Available research API / evidence                                                                           | Missing field or capability                                                                      | Possible later extension                                                                                        |
| ---------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Exact time/date/location/status/description change history | Ordered historical before/after values with visibility rules | Dossier `created_at` / `modified_at`; existing Operations timeline also has only source timestamps          | Source audit records and prior values                                                            | A reviewed source read contract for typed public field changes; never reconstruct a diff from the current state |
| Region / district filtering                                | Authoritative public region identity and geometry membership | `search` supports literal city matching on effective event venues; authoritative source points feed the map | No public research region lookup; existing Geo Scope lookup/import is an administrative workflow | A separate read-only public boundary lookup after data and access review                                        |
| Named source attribution                                   | Public source/provider name                                  | Event `source_link`, venue/organization `web_link`, source update and retrieval times                       | No verified source/provider label on these records                                               | Add only a verified public projection; do not infer providers from external IDs                                 |
| All locations of every event directly on one map           | Bounded occurrence-level map projection                      | Search shows the first matching public date per event; event dossier exposes paginated effective dates      | Separate all-occurrence map response and bounds/cluster contract                                 | A bounded viewport endpoint with the identical filter semantics; no automatic source indexes                    |
| Full relationship network in one view                      | Paginated public relationship traversal                      | Graph/list derives actual organization/event/venue/space/date relationships from the dossier page           | Cross-page graph expansion                                                                       | Public traversal with explicit bounds; never expose the Operations graph's users or memberships                 |
| Saved research                                             | Personal, read-authorized query metadata and ownership       | Reproducible filter URLs                                                                                    | Persistence and ownership contract                                                               | Separate admin metadata migration and authorization design; no placeholder navigation in this MVP               |
| Images for every source record                             | Verified public image association                            | Existing Pluto main/main_logo/main_photo associations and public thumbnail helper                           | Some records have no matching image                                                              | Keep the existing empty-image fallback; never guess image URLs                                                  |

Research intentionally excludes draft/review events, private dates, internal user
or membership data, admin findings/comments/assignments and operator activity.
Organizations and venues are discoverable through public events/occurrences only.
A source record that has no public research context returns 404, even to a system
administrator using Research. Operations remains a separate, broader permission.

The map is page-bounded and explicitly labels its coverage. Monthly activity is
bounded to the latest 120 nonempty months; usage rankings show at most ten entries
per group. No full historical activity or production-scale performance is claimed.
CSV rejects selections above 10,000 records rather than silently truncating them.

Saved searches, watchlists, alerts, notes, collections, advanced statistics,
GeoJSON, polygon analysis, subscriptions and domain write access are follow-ups,
not implemented capabilities. None requires a change to `sndcds/uranus` in this PR.
