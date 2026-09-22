"""Reviewed source contracts for deployment-managed admin schema upgrades.

These fingerprints cover the exact table, index and column inventory at a supported
older Alembic head.  Adding a new target migration does not implicitly authorize an
upgrade: the target and every supported origin must be reviewed and updated here.
"""

ADMIN_UPGRADE_TARGET = "0013"

ADMIN_UPGRADE_CONTRACTS = {
    "0011": {
        "schema_fingerprint": "3e1eaded3cc00f05cc4850b0f6b1bfefba33a2dde289abc68ae64abb70129ea4",
        "target_only_tables": ["assignment", "assignment_event", "finding_event"],
    },
    "0012": {
        "schema_fingerprint": "26fd27303ba8b3c59b56ee8152303f7cfac59a733b926cebcb2856377f65d117",
        "target_only_tables": ["assignment", "assignment_event"],
    },
}
