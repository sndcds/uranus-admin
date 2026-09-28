# Jina knowledge-index plans — operator report recorded 2026-09-28

Source: terminal excerpts supplied by the operator from `awendelk@webserver`,
using `/home/oklab/build/uranus-admin/backend`. Each command loaded
`/etc/uranus-admin/operator.env` and `/etc/uranus-research-ai/client.env`, then ran
`vector_index plan --entity … --model jina-v3 --noncommercial-jina` without a limit.
The [documented jq loop](../../operations.md#3-inspect-a-compact-plan-with-jq)
shows the compact area summary; adding the documented change-count fields produces
the selection supplied here. The values below reproduce the supplied output;
they were not independently rerun when documenting them.

The date records receipt of the excerpts. They contain no execution timestamp,
commit, collection name, model/document version, snapshot hash or exit status.
The three commands ran separately; a shared source snapshot is not established.

## Reported output

Event:

```json
{
  "entity_type": "event",
  "document_count": 583,
  "documents_with_area": 516,
  "area_assignment_coverage": 0.8850771869639794,
  "documents_without_location": 37,
  "chunks": 1154,
  "new": 1154,
  "updated": 0,
  "metadata_updated": 0,
  "deleted": 0
}
```

Venue:

```json
{
  "entity_type": "venue",
  "document_count": 254,
  "documents_with_area": 239,
  "area_assignment_coverage": 0.9409448818897638,
  "documents_without_location": 4,
  "chunks": 285,
  "new": 285,
  "updated": 0,
  "metadata_updated": 0,
  "deleted": 0
}
```

Organization:

```json
{
  "entity_type": "organization",
  "document_count": 139,
  "documents_with_area": 121,
  "area_assignment_coverage": 0.8705035971223022,
  "documents_without_location": 37,
  "chunks": 146,
  "new": 146,
  "updated": 0,
  "metadata_updated": 0,
  "deleted": 0
}
```

## Interpretation

| Entity       | Documents | With area | Area coverage | Without area | Without location | Planned chunks / new |
| ------------ | --------: | --------: | ------------: | -----------: | ---------------: | -------------------: |
| Event        |       583 |       516 |        88.51% |           67 |               37 |          1154 / 1154 |
| Venue        |       254 |       239 |        94.09% |           15 |                4 |            285 / 285 |
| Organization |       139 |       121 |        87.05% |           18 |               37 |            146 / 146 |

Coverage is `documents_with_area / document_count`; percentages are rounded to two
decimal places. “Without area” is derived by subtraction. Area coverage describes
the selected documents, not the completeness of the imported municipality catalog.

Missing location and missing area are different measures. A known point can lack
an area assignment. For organizations, `documents_without_location` counts missing
home points, while `documents_with_area` can include either home or activity areas.
For events, location refers to the effective locations in the document. The counts
alone do not diagnose individual missing assignments or prove DE-SH import completion.

All reported chunks are planned as `new`; `updated`, `metadata_updated` and
`deleted` are zero for every entity. These are planned point changes, not completed
embeddings or writes. A plan uses tokenization and index reads; it neither calls
`/embed` nor writes database rows or Qdrant points. These results do not establish
retrieval quality or successful synchronization. Historical legacy event benchmark
results from [2026-09-27](../2026-09-27/README.md) remain a separate measurement.
