from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from suitsflow.api.dependencies import get_principal
from suitsflow.core.config import Settings
from suitsflow.core.security import Principal
from suitsflow.main import create_app
from suitsflow.schemas.document import DocumentCreate, VersionCreate


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "document_type": "contract"},
        {"name": "x" * 256, "document_type": "contract"},
        {"name": "A", "document_type": "invalid"},
        {"name": "A", "document_type": "contract", "tenant_id": str(uuid4())},
        {"name": "A", "document_type": "contract", "status": "ready"},
    ],
)
def test_invalid_document_metadata(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        DocumentCreate.model_validate(payload)


@pytest.mark.parametrize(
    "override",
    [
        {"file_size": 0},
        {"file_size": 104857601},
        {"file_size": True},
        {"checksum": "bad"},
        {"mime_type": "application/x-executable"},
        {"s3_key": "another-tenant/private.pdf"},
        {"version_number": 100},
    ],
)
def test_invalid_version_metadata(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VersionCreate.model_validate(
            {"mime_type": "application/pdf", "file_size": 12, "checksum": "a" * 64, **override}
        )


@pytest.mark.parametrize("roles", [frozenset(), frozenset({"unknown"})])
def test_documents_require_a_recognized_role(roles: frozenset[str]) -> None:
    app = create_app(Settings(_env_file=None, environment="test"))
    app.dependency_overrides[get_principal] = lambda: Principal(uuid4(), uuid4(), roles)
    with TestClient(app) as client:
        assert client.get("/api/v1/documents").status_code == 403
        assert (
            client.post(
                "/api/v1/documents", json={"name": "A", "document_type": "contract"}
            ).status_code
            == 403
        )


def test_documents_require_authentication() -> None:
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        assert client.get("/api/v1/documents").status_code == 401
        assert (
            client.get(f"/api/v1/documents/{uuid4()}/versions/{uuid4()}/content").status_code == 401
        )
        schema = client.get("/openapi.json").json()
        download = schema["paths"]["/api/v1/documents/{document_id}/versions/{version_id}/content"]
        assert "application/octet-stream" in download["get"]["responses"]["200"]["content"]
