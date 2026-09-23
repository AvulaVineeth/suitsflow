import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.core.config import Settings
from suitsflow.db.session import get_session
from suitsflow.main import create_app


def test_health_returns_process_status() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_ready_returns_readiness_status() -> None:
    app = create_app(Settings(environment="test"))
    session = AsyncMock(spec=AsyncSession)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}
    session.execute.assert_awaited_once()


@pytest.mark.parametrize(
    "error",
    [OperationalError("SELECT 1", {}, Exception("secret")), OSError("secret"), TimeoutError()],
)
def test_ready_returns_sanitized_failure(error: Exception) -> None:
    app = create_app(Settings(environment="test"))
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = error

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
        assert client.get("/api/v1/health").status_code == 200
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_ready_times_out_slow_database() -> None:
    app = create_app(Settings(environment="test", database_timeout_seconds=0.01))
    session = AsyncMock(spec=AsyncSession)

    async def slow_execute(*args: object) -> None:
        await asyncio.sleep(1)

    session.execute.side_effect = slow_execute

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        assert client.get("/api/v1/ready").status_code == 503
