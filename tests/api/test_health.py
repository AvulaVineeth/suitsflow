from fastapi.testclient import TestClient

from suitsflow.core.config import Settings
from suitsflow.main import create_app


def test_health_returns_process_status() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_ready_returns_readiness_status() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}
