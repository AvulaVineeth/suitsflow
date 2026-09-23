import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from suitsflow.core.config import Settings
from suitsflow.core.security import Principal
from suitsflow.db.models import AuditLog, Tenant, User
from suitsflow.db.session import Database
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.tenants import TenantRepository
from suitsflow.schemas.tenant import TenantNameUpdate
from suitsflow.services.tenants import TenantService


def exercise_audited_updates(
    client: TestClient,
    settings: Settings,
    tenant_id: UUID,
    other_id: UUID,
    user_id: UUID,
    headers: dict[str, str],
) -> None:
    endpoint = f"/api/v1/tenants/{tenant_id}"
    for payload in ({"name": " "}, {"name": "x" * 256}, {"name": "Valid", "status": "suspended"}):
        assert client.patch(endpoint, json=payload, headers=headers).status_code == 422
    assert client.patch(endpoint, json={"name": "Unauthorized"}).status_code == 401
    assert (
        client.patch(
            f"/api/v1/tenants/{other_id}", json={"name": "Cross tenant"}, headers=headers
        ).status_code
        == 404
    )
    response = client.patch(endpoint, json={"name": "  Renamed Legal  "}, headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Legal"
    assert (
        client.patch(endpoint, json={"name": "Renamed Legal"}, headers=headers).status_code == 200
    )

    async def verify_storage() -> None:
        db = Database(settings)
        principal = Principal(user_id, tenant_id, frozenset({"tenant_admin"}))
        try:
            async with db.sessions() as session:
                logs = (await session.scalars(select(AuditLog))).all()
                assert len(logs) == 1
                log = logs[0]
                assert (log.tenant_id, log.user_id, log.resource_id) == (
                    tenant_id,
                    user_id,
                    tenant_id,
                )
                assert log.action == "tenant.name_updated"
                assert log.details == {
                    "name": {"before": "Updated Legal", "after": "Renamed Legal"}
                }
                assert log.created_at.tzinfo is not None
                for statement in (
                    update(AuditLog).values(action="tampered"),
                    delete(AuditLog),
                    text("TRUNCATE audit_logs"),
                ):
                    with pytest.raises(DBAPIError, match="append-only"):
                        await session.execute(statement)
                    await session.rollback()
                other_user = await session.scalar(select(User.id).where(User.tenant_id == other_id))
                session.add(
                    AuditLog(
                        tenant_id=tenant_id,
                        user_id=other_user,
                        action="invalid",
                        resource_type="tenant",
                        resource_id=tenant_id,
                        details={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
                with (
                    patch.object(
                        AuditRepository,
                        "record_tenant_name_change",
                        new=AsyncMock(side_effect=RuntimeError("audit failure")),
                    ),
                    pytest.raises(RuntimeError, match="audit failure"),
                ):
                    await TenantService(TenantRepository(session)).update_name(
                        principal, tenant_id, TenantNameUpdate(name="Must roll back")
                    )
                assert (
                    await session.scalar(select(Tenant.name).where(Tenant.id == tenant_id))
                    == "Renamed Legal"
                )
                assert len((await session.scalars(select(AuditLog))).all()) == 1

            async def rename(name: str) -> None:
                async with db.sessions() as session:
                    await TenantService(TenantRepository(session)).update_name(
                        principal, tenant_id, TenantNameUpdate(name=name)
                    )

            await asyncio.gather(rename("Concurrent A"), rename("Concurrent B"))
            async with db.sessions() as session:
                logs = (await session.scalars(select(AuditLog))).all()
                assert len(logs) == 3
                transitions = {
                    log.details["name"]["before"]: log.details["name"]["after"] for log in logs
                }
                first = transitions["Renamed Legal"]
                last = transitions[first]
                assert {first, last} == {"Concurrent A", "Concurrent B"}
                assert (
                    await session.scalar(select(Tenant.name).where(Tenant.id == tenant_id)) == last
                )
        finally:
            await db.dispose()

    asyncio.run(verify_storage())
