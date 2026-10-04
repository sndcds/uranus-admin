"""Reviewed source contracts for deployment-managed admin schema upgrades.

These fingerprints cover the exact table, index and column inventory at a supported
older Alembic head.  Adding a new target migration does not implicitly authorize an
upgrade: the target and every supported origin must be reviewed and updated here.
"""

ADMIN_UPGRADE_TARGET = "0019"

ADMIN_UPGRADE_CONTRACTS = {
    "0011": {
        "schema_fingerprint": "3e1eaded3cc00f05cc4850b0f6b1bfefba33a2dde289abc68ae64abb70129ea4",
        "target_only_tables": [
            "assignment",
            "assignment_event",
            "finding_event",
            "auth_journalist",
            "research_area",
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0012": {
        "schema_fingerprint": "26fd27303ba8b3c59b56ee8152303f7cfac59a733b926cebcb2856377f65d117",
        "target_only_tables": [
            "assignment",
            "assignment_event",
            "auth_journalist",
            "research_area",
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0013": {
        "schema_fingerprint": "313c96c1dc176d098999921bd4e0c53943b86b0498c4f2f83d7542cf67003f04",
        "target_only_tables": [
            "auth_journalist",
            "research_area",
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0014": {
        "schema_fingerprint": "633a2cf40ce9870a581537e5338cebad1e81bdfeaada54ad21930ae37862f0d9",
        "target_only_tables": [
            "auth_journalist",
            "research_area",
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0015": {
        "schema_fingerprint": "34eb17c34d1c761f893e9658d411158865d225a87b264d6d0ca57caf4a0e3d49",
        "target_only_tables": [
            "research_area",
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0016": {
        "schema_fingerprint": "13bf0523a4626b2a9fa29c201ef75e89db9ef3d468b3a0503e50ea908656928c",
        "target_only_tables": [
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    "0017": {
        "schema_fingerprint": "13bf0523a4626b2a9fa29c201ef75e89db9ef3d468b3a0503e50ea908656928c",
        "target_only_tables": [
            "research_query_history",
            "research_query_suggestion",
            "research_query_suggestion_event",
        ],
    },
    # Recomputed from Alembic's offline 0018 inventory by
    # tests/test_admin_upgrade_contracts.py using the deployment fingerprint.
    # 0019 only widens research_area_type; tables, columns, indexes and grants stay unchanged.
    "0018": {
        "schema_fingerprint": "8ec0112176bb414a9ada75c356e1a61e2226aebef5764d09f9e24f5df9a27b50",
        "target_only_tables": [],
    },
}
