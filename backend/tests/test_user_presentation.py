"""Canonical labels across protected HTTP surfaces, backed by real PostgreSQL."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import get_connection
from app.main import create_app
from app.repositories.quality_sources import load_sources
from app.repositories.user_presentation import USER_DISPLAY_LABEL_SQL
from app.services.inbox import source_presentations
from app.services.quality.core import evaluate_core
from tests.conftest import uid

pytestmark = pytest.mark.integration
EMAIL = "max@example.org"
KEY = str(uid(1))
MEMBERSHIP = f"membership:{uid(10)}:{KEY}"


@pytest.fixture
async def presentation_client(db_connection, settings):
    async def connection():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.parametrize(
    "display_name,username,email,label,subtitle",
    [
        ("Max Mustermann", "max", EMAIL, "Max Mustermann", f"@max · {EMAIL}"),
        (None, "max", EMAIL, "max", EMAIL),
        ("", "max", EMAIL, "max", EMAIL),
        (None, None, EMAIL, EMAIL, None),
        ("", "", EMAIL, EMAIL, None),
        (None, "", EMAIL, EMAIL, None),
        ("", None, EMAIL, EMAIL, None),
        (None, None, "", KEY, None),
        ("", "", "", KEY, None),
        (EMAIL, "max", EMAIL, EMAIL, "@max"),
        ("@max", "max", EMAIL, "@max", EMAIL),
    ],
)
async def test_labels_across_admin_surfaces(
    presentation_client,
    db_connection,
    settings,
    now,
    headers,
    display_name,
    username,
    email,
    label,
    subtitle,
    caplog,
):
    # Transaction-local test rows only; source email is NOT NULL in the verified DDL.
    await db_connection.execute(
        text(
            'UPDATE uranus."user" SET display_name=:name,username=:username,email=:email '
            "WHERE uuid=:id"
        ),
        {"name": display_name, "username": username, "email": email, "id": uid(1)},
    )

    async def get(path, **params):
        response = await presentation_client.get(f"/api/v1/{path}", params=params, headers=headers)
        assert response.status_code == 200, response.text
        for secret in ("password_hash", "not-a-password-hash", "activate_token"):
            assert secret not in response.text
        return response.json()

    for kind, key in (("user", KEY), ("team_membership", MEMBERSHIP)):
        activity = await get("dashboard/activity", entity_type=kind, entity_key=key)
        assert activity["items"][0]["entity_name"] == label
        assert activity["items"][0]["public_url"] is None

    search = await get("entity-search", entity_type="user", q=email or KEY)
    assert search["items"][0]["label"] == label
    assert search["items"][0]["subtitle"] == subtitle
    users = await get("users", q=email or KEY)
    assert users["items"][0]["entity_name"] == label
    detail = await get(f"users/{KEY}")
    assert detail["item"]["entity_name"] == label
    assert detail["item"]["entity_key"] == KEY
    membership = next(i for i in detail["related"]["items"] if i["entity_key"] == MEMBERSHIP)
    assert membership["entity_name"] == label
    organization = await get(f"organizations/{uid(10)}")
    for item in organization["related"]["items"]:
        if item["entity_type"] in {"user", "team_membership"}:
            assert item["entity_name"] == label

    for kind, key in (("user", KEY), ("organization", str(uid(10)))):
        graph = await get("graph", root_type=kind, root_key=key, depth=2)
        node = next(n for n in graph["nodes"] if n["type"] == "user" and n["key"] == KEY)
        assert node["label"] == label
        assert node["public_url"] is None
        assert node["admin_url"] == f"/users/{KEY}"
    graph_search = await get("graph/search", entity_type="user", q=label)
    assert graph_search["items"][0]["label"] == label

    for queue in ("team_invitations", "user_activation", "partner_requests"):
        result = await get(f"work-queues/{queue}")
        assert result["items"][0]["user_name"] == label
    presentations = await source_presentations(
        db_connection,
        [
            {"entity_type": "user", "entity_key": KEY},
            {"entity_type": "team_membership", "entity_key": MEMBERSHIP},
        ],
    )
    assert presentations[("user", KEY)]["entity_name"] == label
    assert presentations[("team_membership", MEMBERSHIP)]["entity_name"] == label
    await db_connection.execute(
        text(
            "UPDATE uranus.organization_member_link SET has_joined=true,accept_token='test-secret' "
            "WHERE user_uuid=:id"
        ),
        {"id": uid(1)},
    )
    sources = await load_sources(db_connection, uid(10))
    findings = evaluate_core("membership_joined_accept_token_present", sources, settings, now)
    assert findings.findings[0].entity_name == label
    assert "test-secret" not in findings.findings[0].model_dump_json()
    assert EMAIL not in caplog.text


async def test_null_email_semantics_without_relaxing_source_constraints(db_connection):
    # NULL email is not allowed by source DDL, but the expression also handles it.
    value = await db_connection.scalar(
        text(
            f"SELECT {USER_DISPLAY_LABEL_SQL} FROM (SELECT CAST(:id AS uuid) uuid,"
            "NULL::text display_name,NULL::text username,NULL::text email) u"
        ),
        {"id": uid(1)},
    )
    assert value == KEY


@pytest.mark.parametrize(
    "path,params",
    [
        ("dashboard/activity", {"entity_type": "user"}),
        ("dashboard/activity", {"entity_type": "team_membership"}),
        ("entity-search", {"entity_type": "user", "q": "max"}),
        ("users", {}),
        (f"users/{KEY}", {}),
        ("graph", {"root_type": "user", "root_key": KEY}),
        ("graph/search", {"entity_type": "user", "q": "max"}),
        ("work-queues/team_invitations", {}),
        ("inbox", {}),
        (f"entities/user/{KEY}/timeline", {}),
    ],
)
async def test_user_presentation_requires_admin(presentation_client, path, params):
    response = await presentation_client.get(f"/api/v1/{path}", params=params)
    assert response.status_code == 401
    assert EMAIL not in response.text
    assert "fixture@example.invalid" not in response.text
