import pytest
from pydantic import ValidationError

from app.schemas.action import Action


def test_actions_are_generated_from_known_routes():
    action = Action(route="partner_requests", entity_key="partner-request:a:b&url=//evil")
    assert (
        action.href
        == "/queues/partner_requests?entity_key=partner-request%3Aa%3Ab%26url%3D%2F%2Fevil"
    )
    with pytest.raises(ValidationError):
        Action(route="https://evil.invalid", entity_key="a")
