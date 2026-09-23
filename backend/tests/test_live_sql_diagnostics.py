"""Regression coverage for live identities; no source writes or full quality scans."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest

from app.errors import APIError
from app.schemas.finding import Finding, FindingFilters
from app.services.quality.engine import findings_page
from app.sql_diagnostics.executor import definition, execute
from app.sql_diagnostics.identity import live_finding
from tests.conftest import uid

IDENTITY = f"venue_missing_location:venue:{uid(20)}:point"


def test_live_definition_uses_registry_without_fabricated_observation():
    context = live_finding(IDENTITY)
    result = definition(context)
    assert result.last_seen_at is None
    assert result.parameters == {"entity_key": str(uid(20)), "diagnostic_limit": 50}
    assert result.readonly is True
    assert result.recipe_id == "venue_missing_location"
    key = f"membership:{uid(10)}:{uid(1)}"
    membership = live_finding(
        f"membership_joined_accept_token_present:team_membership:{quote(key, safe='')}:accept_token"
    )
    assert definition(membership).parameters["org_uuid"] == str(uid(10))
    assert "accept_token_present" in definition(membership).columns
    assert "accept_token" not in definition(membership).columns


@pytest.mark.parametrize(
    "identity",
    [
        "missing",
        IDENTITY + ":extra",
        IDENTITY.replace("venue_missing_location", "unknown_rule"),
        IDENTITY.replace(":venue:", ":event:"),
        IDENTITY.replace(":point", ":password_hash"),
        IDENTITY.replace(str(uid(20)), "not-a-uuid"),
        IDENTITY.replace(str(uid(20)), quote("'; DROP TABLE uranus.venue; --", safe="")),
        IDENTITY.replace("venue_missing_location", "%76enue_missing_location"),
        "membership_joined_accept_token_present:team_membership:membership%253Abad:accept_token",
    ],
)
def test_live_identity_rejects_unknown_recipes_incompatible_fields_and_injection(identity):
    with pytest.raises(APIError) as error:
        live_finding(identity)
    assert error.value.code in {"diagnostic_invalid_finding", "diagnostic_unavailable"}


async def test_live_api_requires_auth_and_preserves_strict_request_boundary(client, headers):
    url = "/api/v1/findings/sql-diagnostic"
    params = {"finding_id": IDENTITY, "mode": "live"}
    with (
        patch("app.api.sql_diagnostics.load_finding", new_callable=AsyncMock) as stored,
        patch("app.api.sql_diagnostics.execute", new_callable=AsyncMock) as executor,
    ):
        assert (await client.get(url, params=params)).status_code == 401
        assert (await client.post(url + "/execute", json=params)).status_code == 401
        result = await client.get(url, params=params, headers=headers)
        assert result.status_code == 200
        assert result.json()["last_seen_at"] is None
        stored.assert_not_called()
        executor.assert_not_called()
        for extra in ({"sql": "SELECT 1"}, {"mode": "unknown"}, {"entity_key": str(uid(1))}):
            assert (
                await client.get(url, params={**params, **extra}, headers=headers)
            ).status_code == 422
            assert (
                await client.post(url + "/execute", json={**params, **extra}, headers=headers)
            ).status_code == 422
        assert (
            await client.post(url + "/execute?mode=live", json=params, headers=headers)
        ).status_code == 422
        executor.assert_not_called()
        executor.side_effect = APIError(503, "diagnostic_failed", "Diagnostic unavailable.")
        response = await client.post(url + "/execute", json=params, headers=headers)
        assert response.status_code == 503
        assert executor.call_args.args[1] == live_finding(IDENTITY)
        stored.assert_not_called()


async def test_live_execute_reuses_bounded_reader_and_current_evaluation(settings):
    stamp = datetime(2026, 9, 23, tzinfo=UTC)
    columns = definition(live_finding(IDENTITY)).columns
    row = {key: None for key in columns}
    row.update(uuid=uid(20), name="Synthetic venue", point_missing=True)
    with patch(
        "app.sql_diagnostics.executor.read_registered_rows",
        new_callable=AsyncMock,
        return_value=([row], stamp),
    ) as read:
        result = await execute(AsyncMock(), live_finding(IDENTITY), settings, "admin:synthetic")
    assert result.observed_at == stamp
    assert result.evaluation.matched is True
    assert read.call_args.args[1].parameters == {"entity_key": uid(20), "diagnostic_limit": 50}


def test_live_page_advertises_only_supported_diagnostics():
    stamp = datetime(2026, 9, 23, tzinfo=UTC)
    item = Finding(
        id=IDENTITY,
        rule="venue_missing_location",
        severity="warning",
        priority=4,
        priority_score=1,
        priority_reasons=[],
        entity_type="venue",
        entity_key=str(uid(20)),
        entity_name="Synthetic venue",
        organization_id=None,
        organization_name=None,
        field="point",
        message="Geoposition fehlt",
        last_seen_at=stamp,
    )
    unsupported = item.model_copy(update={"id": "unsupported", "rule": "unsupported"})
    page = findings_page([item, unsupported], FindingFilters(mode="live"), stamp)
    assert {entry.id: entry.sql_diagnostic_available for entry in page.items} == {
        IDENTITY: True,
        "unsupported": False,
    }
