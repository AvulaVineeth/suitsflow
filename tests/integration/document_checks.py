import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from suitsflow.core.config import Settings
from suitsflow.core.security import Principal
from suitsflow.db.models import AuditLog, Document, DocumentVersion, Role, User, UserRole
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.document import DocumentCreate, VersionCreate
from suitsflow.services.documents import DocumentService


def exercise_documents(
    client: TestClient, settings: Settings, other_tenant: UUID, headers: dict[str, str]
) -> None:
    tenant_id, user_id = settings.development_tenant_id, settings.development_user_id
    assert tenant_id is not None and user_id is not None
    payload = {"name": "  Example agreement  ", "document_type": "contract"}
    version_payload = {"mime_type": "application/pdf", "file_size": 12, "checksum": "a" * 64}
    response = client.post("/api/v1/documents", json=payload, headers=headers)
    assert response.status_code == 201
    document_id = UUID(response.json()["id"])
    assert response.json()["name"] == "Example agreement"
    assert response.json()["status"] == "draft"
    assert response.json()["created_by"] == str(user_id)
    endpoint = f"/api/v1/documents/{document_id}"
    assert client.get(endpoint, headers=headers).status_code == 200
    assert client.get(endpoint + "/versions", headers=headers).json() == []
    version = client.post(endpoint + "/versions", json=version_payload, headers=headers)
    assert version.status_code == 201
    assert version.json()["version_number"] == 1
    assert client.get(endpoint, headers=headers).json()["status"] == "draft"
    assert client.get("/api/v1/documents?limit=101", headers=headers).status_code == 422

    async def verify_database() -> tuple[UUID, UUID]:
        db = Database(settings)
        principal = Principal(user_id, tenant_id, frozenset({"tenant_admin"}))
        member_id = uuid4()
        try:
            async with db.sessions() as session:
                other_user_id = await session.scalar(
                    select(User.id).where(User.tenant_id == other_tenant)
                )
                assert other_user_id is not None
                foreign = Document(
                    tenant_id=other_tenant,
                    name="Private",
                    document_type="policy",
                    created_by=other_user_id,
                )
                member_role = Role(tenant_id=tenant_id, name="member")
                session.add_all(
                    [
                        foreign,
                        member_role,
                        User(
                            id=member_id,
                            tenant_id=tenant_id,
                            name="Reader",
                            email="reader@example.com",
                        ),
                    ]
                )
                await session.flush()
                foreign_id = foreign.id
                session.add(
                    UserRole(tenant_id=tenant_id, user_id=member_id, role_id=member_role.id)
                )
                await session.commit()
                invalid_records = [
                    Document(
                        tenant_id=tenant_id,
                        name="Wrong actor",
                        document_type="contract",
                        created_by=other_user_id,
                    )
                ]
                for record in invalid_records:
                    session.add(record)
                    with pytest.raises(IntegrityError):
                        await session.flush()
                    await session.rollback()
                for overrides in (
                    {"document_id": foreign_id},
                    {"created_by": other_user_id},
                    {"version_number": 1},
                    {"version_number": 0},
                    {"file_size": 0},
                    {"checksum": "bad"},
                ):
                    session.add(
                        DocumentVersion(
                            **{
                                "tenant_id": tenant_id,
                                "document_id": document_id,
                                "created_by": user_id,
                                "version_number": 10,
                                **version_payload,
                                **overrides,
                            }
                        )
                    )
                    with pytest.raises(IntegrityError):
                        await session.flush()
                    await session.rollback()
                service = DocumentService(DocumentRepository(session))
                with patch.object(
                    AuditRepository,
                    "record_document_event",
                    new=AsyncMock(side_effect=RuntimeError("audit failure")),
                ):
                    with pytest.raises(RuntimeError):
                        await service.create(
                            principal, DocumentCreate(name="Rollback", document_type="other")
                        )
                    with pytest.raises(RuntimeError):
                        await service.add_version(
                            principal, document_id, VersionCreate.model_validate(version_payload)
                        )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(Document.tenant_id == tenant_id)
                    )
                    == 1
                )
                assert await session.scalar(select(func.count()).select_from(DocumentVersion)) == 1

            async def append_version() -> int:
                async with db.sessions() as session:
                    result = await DocumentService(DocumentRepository(session)).add_version(
                        principal, document_id, VersionCreate.model_validate(version_payload)
                    )
                    return result.version_number

            assert sorted(await asyncio.gather(append_version(), append_version())) == [2, 3]
            async with db.sessions() as session:
                events = (
                    await session.scalars(
                        select(AuditLog).where(AuditLog.resource_id == document_id)
                    )
                ).all()
                assert len(events) == 4
                assert {event.action for event in events} == {
                    "document.created",
                    "document.version_registered",
                }
            return foreign_id, member_id
        finally:
            await db.dispose()

    foreign_id, member_id = asyncio.run(verify_database())
    for inaccessible_id in (foreign_id, uuid4()):
        hidden = f"/api/v1/documents/{inaccessible_id}"
        for path in (hidden, hidden + "/versions"):
            assert client.get(path, headers=headers).status_code == 404
        assert (
            client.post(hidden + "/versions", json=version_payload, headers=headers).status_code
            == 404
        )
    assert [row["id"] for row in client.get("/api/v1/documents", headers=headers).json()] == [
        str(document_id)
    ]
    assert client.get("/api/v1/documents?offset=1", headers=headers).json() == []
    assert [
        row["version_number"]
        for row in client.get(endpoint + "/versions?limit=2&offset=1", headers=headers).json()
    ] == [2, 3]
    member_settings = settings.model_copy(update={"development_user_id": member_id})
    with TestClient(create_app(member_settings)) as member:
        assert member.get(endpoint, headers=headers).status_code == 200
        assert member.get(endpoint + "/versions", headers=headers).status_code == 200
        assert member.post("/api/v1/documents", json=payload, headers=headers).status_code == 403
        assert (
            member.post(endpoint + "/versions", json=version_payload, headers=headers).status_code
            == 403
        )
