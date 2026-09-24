"""Run only against an explicitly supplied, empty, disposable test database."""

import asyncio
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from tests.integration.audit_checks import exercise_audited_updates
from tests.integration.document_checks import exercise_documents
from tests.integration.membership_checks import (
    exercise_memberships,
    revoke_roles,
    set_access_status,
)
from tests.integration.scan_job_checks import exercise_scan_jobs
from tests.integration.upload_checks import exercise_uploads

from suitsflow.core.config import Settings, get_settings
from suitsflow.db.models import DocumentVersion, Tenant
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.tenants import TenantRepository

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
        tenant_id, other_tenant_id, suspended_tenant_id = uuid4(), uuid4(), uuid4()

        async def exercise_sessions() -> None:
            db = Database(settings)
            try:
                async with db.sessions() as session:
                    session.add(Tenant(id=tenant_id, name="Example Legal"))
                    session.add(Tenant(id=other_tenant_id, name="Other Legal"))
                    session.add(
                        Tenant(id=suspended_tenant_id, name="Suspended", status="suspended")
                    )
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
                async with db.sessions() as session:
                    repository = TenantRepository(session)
                    assert await repository.get_active(tenant_scope=tenant_id, tenant_id=tenant_id)
                    assert (
                        await repository.get_active(
                            tenant_scope=tenant_id, tenant_id=other_tenant_id
                        )
                        is None
                    )
                    assert (
                        await repository.get_active(
                            tenant_scope=suspended_tenant_id, tenant_id=suspended_tenant_id
                        )
                        is None
                    )
            finally:
                await db.dispose()

        asyncio.run(exercise_sessions())
        user_id = asyncio.run(exercise_memberships(settings, tenant_id, other_tenant_id))
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/ready").status_code == 200
        token = "integration-only-token-at-least-32-characters"
        auth_settings = Settings(
            database_url=url,
            environment="test",
            development_auth_enabled=True,
            development_auth_token=SecretStr(token),
            development_user_id=user_id,
            development_tenant_id=tenant_id,
        )
        with TestClient(create_app(auth_settings)) as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
            assert response.status_code == 200
            assert response.json()["id"] == str(tenant_id)
            assert response.json()["name"] == "Updated Legal"
            assert set(response.json()) == {"id", "name", "status", "created_at", "updated_at"}
            for invisible_id in (other_tenant_id, suspended_tenant_id, uuid4()):
                response = client.get(
                    f"/api/v1/tenants/{invisible_id}",
                    headers={**headers, "X-Tenant-ID": str(invisible_id)},
                )
                assert response.status_code == 404
                assert response.json() == {"detail": "Tenant not found"}
            exercise_audited_updates(client, settings, tenant_id, other_tenant_id, user_id, headers)
            exercise_documents(client, auth_settings, other_tenant_id, headers)
            exercise_uploads(auth_settings, other_tenant_id, headers)
            exercise_scan_jobs(auth_settings, other_tenant_id, headers)
            asyncio.run(set_access_status(settings, user_id, tenant_id, active=False))
            assert client.get(f"/api/v1/tenants/{tenant_id}", headers=headers).status_code == 403
            asyncio.run(set_access_status(settings, user_id, tenant_id, active=True))
            assert client.get(f"/api/v1/tenants/{tenant_id}", headers=headers).status_code == 200
            asyncio.run(revoke_roles(settings, user_id))
            response = client.get(
                f"/api/v1/tenants/{tenant_id}", headers={**headers, "X-Role": "tenant_admin"}
            )
            assert response.status_code == 403
        suspended_settings = auth_settings.model_copy(
            update={"development_tenant_id": suspended_tenant_id}
        )
        with TestClient(create_app(suspended_settings)) as client:
            assert (
                client.get(f"/api/v1/tenants/{suspended_tenant_id}", headers=headers).status_code
                == 403
            )
        for invalid_user in (uuid4(),):
            unknown_settings = auth_settings.model_copy(
                update={"development_user_id": invalid_user}
            )
            with TestClient(create_app(unknown_settings)) as client:
                response = client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
                assert response.status_code == 403
                assert response.json() == {"detail": "Access denied"}
        invalid_url = make_url(url).set(password="incorrect-test-password")
        invalid_settings = Settings(
            database_url=invalid_url.render_as_string(hide_password=False), environment="test"
        )
        with TestClient(create_app(invalid_settings)) as client:
            response = client.get("/api/v1/ready")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}
            assert client.get("/api/v1/health").status_code == 200
        # Upgrading a database with existing stored files must quarantine every upload.
        command.downgrade(config, "0005")
        command.upgrade(config, "head")

        async def verify_existing_uploads_are_quarantined() -> None:
            db = Database(settings)
            try:
                async with db.sessions() as session:
                    versions = (await session.scalars(select(DocumentVersion))).all()
                    assert any(version.uploaded_at is not None for version in versions)
                    for version in versions:
                        assert version.scanned_at is None
                        assert version.content_status == (
                            "pending_scan" if version.uploaded_at is not None else "pending_upload"
                        )
            finally:
                await db.dispose()

        asyncio.run(verify_existing_uploads_are_quarantined())
        command.downgrade(config, "0001")
        assert sorted(asyncio.run(tables())) == ["alembic_version", "tenants"]
        command.upgrade(config, "head")
        command.check(config)
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
