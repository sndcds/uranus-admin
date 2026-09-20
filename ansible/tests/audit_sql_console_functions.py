"""Emit a REVIEW CANDIDATE from a fresh CI-image database; never edit the contract.

Create a separate *_test database FROM template0 and install only postgis first.
Run with ANSIBLE_TEST_DATABASE_URL. Reads catalogs in a READ ONLY transaction.
The output must be reviewed with the pinned image/source before committing it.
"""

import importlib.util
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "ansible/roles/uranus_admin/library/uranus_sql_console.py"
CONTRACT = ROOT / "ansible/roles/uranus_admin/files/sql_console_contract.json"


def main():
    url = os.environ["ANSIBLE_TEST_DATABASE_URL"]
    parsed = urlsplit(url)
    if (
        parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"/[a-z][a-z0-9_]*_test", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Only explicitly disposable local test databases")
    spec = importlib.util.spec_from_file_location("boundary", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = json.loads(CONTRACT.read_text())
    with psycopg2.connect(url) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL search_path=pg_catalog")
            cur.execute("SELECT extname,extversion FROM pg_extension ORDER BY extname")
            extensions = dict(cur.fetchall())
            if set(extensions) != {"plpgsql", "postgis"}:
                raise ValueError("Audit requires fresh template0 database with only postgis")
            cur.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname IN ('uranus','admin','uranus_console')"
            )
            if cur.fetchone():
                raise ValueError("Refuse application schemas in catalog audit database")
        functions = module.function_catalog(conn)
        groups = {"core": [], "plpgsql": [], "postgis": []}
        for function in functions:
            group = function["extension"] or "core"
            if group not in groups or (
                group == "core" and function["schema"] not in {"pg_catalog", "information_schema"}
            ):
                raise ValueError("Unreviewed function in audit input")
            groups[group].append(function)
        result = {"postgresql_major": conn.server_version // 10000, "groups": {}}
        for name, members in groups.items():
            entry = {
                "version": extensions.get(name),
                "catalog_sha256": module.function_set_digest(members),
                "functions": len(members),
                "restricted_functions": {},
            }
            for function in members:
                if not module.restricted_function(function, contract["function_policy"]):
                    continue
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT a.grantee,r.rolname FROM pg_proc p,
                        LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                        LEFT JOIN pg_roles r ON r.oid=a.grantee
                        WHERE p.oid=%s AND a.privilege_type='EXECUTE' AND a.grantee<>p.proowner
                        ORDER BY r.rolname""",
                        (function["oid"],),
                    )
                    grants = cur.fetchall()
                entry["restricted_functions"][function["signature"]] = {
                    "public_execute": any(oid == 0 for oid, _ in grants),
                    "privileged_grantees": [role for oid, role in grants if oid != 0],
                    "definition_sha256": function["definition_sha256"],
                }
            result["groups"][name] = entry
        result["groups"]["postgis"]["metadata_select"] = {
            f["schema"] + "." + f["name"]: f["definition_sha256"]
            for f in module.postgis_metadata(conn)
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
