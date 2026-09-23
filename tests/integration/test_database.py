"""Run only against an explicitly supplied, empty, disposable test database."""

import asyncio
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from suitsflow.core.config import Settings, get_settings
from suitsflow.db.models import Tenant
from suitsflow.db.session import Database
from suitsflow.main import create_app

pytestmark = pytest.mark.integration


def test_postgresql_migrations_sessions_and_readiness(
    pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = os.environ.get("SUITSFLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set SUITSFLOW_TEST_DATABASE_URL to an empty disposable PostgreSQL database")
    assert (make_url(url).database or "").endswith("_test"), "Test database must end in _test"
    settings = Settings(database_url=url, environment="test")

    async def tables() -> list[str]:
        db = Database(settings)
        try:
            async with db.engine.connect() as connection:
                return await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        finally:
            await db.dispose()

    assert asyncio.run(tables()) == [], "Refusing to migrate a nonempty test database"
    monkeypatch.setenv("SUITSFLOW_DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(pytestconfig.rootpath / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.check(config)

        async def exercise_sessions() -> None:
            db = Database(settings)
            try:
                tenant_id = uuid4()
                async with db.sessions() as session:
                    session.add(Tenant(id=tenant_id, name="Example Legal"))
                    await session.commit()
                async with db.sessions() as session:
                    tenant = await session.get(Tenant, tenant_id)
                    assert tenant is not None
                    assert tenant.status == "active"
                    assert tenant.created_at.tzinfo is not None
                    tenant.name = "Updated Legal"
                    await session.commit()
                    await session.refresh(tenant)
                    assert tenant.updated_at >= tenant.created_at
                async with db.sessions() as session:
                    session.add(Tenant(name="Uncommitted"))
                    await session.flush()
                async with db.sessions() as session:
                    assert (
                        await session.scalar(select(Tenant).where(Tenant.name == "Uncommitted"))
                        is None
                    )
                for values in ({"name": " "}, {"name": "Bad", "status": "invalid"}):
                    async with db.sessions() as session:
                        session.add(Tenant(**values))
                        with pytest.raises(IntegrityError):
                            await session.commit()
                        await session.rollback()
                        assert await session.scalar(text("SELECT 1")) == 1
            finally:
                await db.dispose()

        asyncio.run(exercise_sessions())
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/ready").status_code == 200
        invalid_url = make_url(url).set(password="incorrect-test-password")
        invalid_settings = Settings(
            database_url=invalid_url.render_as_string(hide_password=False), environment="test"
        )
        with TestClient(create_app(invalid_settings)) as client:
            response = client.get("/api/v1/ready")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
            assert client.get("/api/v1/health").status_code == 200
        command.downgrade(config, "base")
        assert asyncio.run(tables()) == ["alembic_version"]
        command.upgrade(config, "head")
        command.check(config)
    finally:
        command.downgrade(config, "base")
        get_settings.cache_clear()

        async def remove_version_table() -> None:
            db = Database(settings)
            try:
                async with db.engine.begin() as connection:
                    await connection.execute(text("DROP TABLE alembic_version"))
            finally:
                await db.dispose()

        asyncio.run(remove_version_table())
