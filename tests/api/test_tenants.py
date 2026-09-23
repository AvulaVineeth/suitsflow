from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from suitsflow.core.config import Settings
from suitsflow.main import create_app

TOKEN = "test-only-token-with-at-least-32-characters"


def development_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "development_auth_enabled": True,
        "development_auth_token": SecretStr(TOKEN),
        "development_user_id": uuid4(),
        "development_tenant_id": uuid4(),
        "development_role": "tenant_admin",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("authorization", [None, "Bearer wrong", "Basic abc", "Bearer"])
def test_invalid_identity_is_rejected_without_database(authorization: str | None) -> None:
    settings = development_settings()
    headers = {"Authorization": authorization} if authorization else {}
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/v1/tenants/{settings.development_tenant_id}", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_development_auth_is_disabled_by_default() -> None:
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        response = client.get(
            f"/api/v1/tenants/{uuid4()}", headers={"Authorization": f"Bearer {TOKEN}"}
        )
    assert response.status_code == 401


def test_member_cannot_read_tenant_administration() -> None:
    settings = development_settings(development_role="member")
    with TestClient(create_app(settings)) as client:
        response = client.get(
            f"/api/v1/tenants/{settings.development_tenant_id}",
            headers={"Authorization": f"Bearer {TOKEN}", "X-Role": "tenant_admin"},
        )
    assert response.status_code == 403


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_development_auth_cannot_be_enabled_in_deployed_environments(environment: str) -> None:
    with pytest.raises(ValidationError, match="local/test"):
        development_settings(environment=environment)


@pytest.mark.parametrize(
    "overrides",
    [
        {"development_auth_token": None},
        {"development_auth_token": SecretStr("short")},
        {"development_user_id": None},
        {"development_tenant_id": None},
    ],
)
def test_development_auth_requires_complete_configuration(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="needs IDs"):
        development_settings(**overrides)
