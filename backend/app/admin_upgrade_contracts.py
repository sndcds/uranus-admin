"""Reviewed source contracts for deployment-managed admin schema upgrades.

These fingerprints cover the exact table, index and column inventory at a supported
older Alembic head.  Adding a new target migration does not implicitly authorize an
upgrade: the target and every supported origin must be reviewed and updated here.
"""

ADMIN_UPGRADE_TARGET = "0015"

ADMIN_UPGRADE_CONTRACTS = {
    "0011": {
        "schema_fingerprint": "3e1eaded3cc00f05cc4850b0f6b1bfefba33a2dde289abc68ae64abb70129ea4",
        "target_only_tables": [
            "assignment",
            "assignment_event",
            "finding_event",
            "auth_journalist",
        ],
    },
    "0012": {
        "schema_fingerprint": "26fd27303ba8b3c59b56ee8152303f7cfac59a733b926cebcb2856377f65d117",
        "target_only_tables": ["assignment", "assignment_event", "auth_journalist"],
    },
    "0013": {
        "schema_fingerprint": "313c96c1dc176d098999921bd4e0c53943b86b0498c4f2f83d7542cf67003f04",
        "target_only_tables": ["auth_journalist"],
    },
    "0014": {
        "schema_fingerprint": "633a2cf40ce9870a581537e5338cebad1e81bdfeaada54ad21930ae37862f0d9",
        "target_only_tables": ["auth_journalist"],
    },
}
