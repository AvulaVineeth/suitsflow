import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import BinaryIO
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from suitsflow.api.routes.documents import get_storage
from suitsflow.core.config import Settings
from suitsflow.db.models import AuditLog, DocumentVersion, Role, User, UserRole
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.services.storage import StorageUnavailable, StoredObject


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False

    def put(
        self, key: str, body: BinaryIO, *, size: int, checksum: str, mime_type: str
    ) -> StoredObject:
        if self.fail:
            raise StorageUnavailable
        content = body.read()
        assert len(content) == size
        assert hashlib.sha256(content).hexdigest() == checksum
        assert key not in self.objects
        self.objects[key] = content
        return StoredObject("private-test", key, "s3-version-id")


def exercise_uploads(settings: Settings, other_tenant: UUID, headers: dict[str, str]) -> None:
    storage = MemoryStorage()
    app = create_app(settings)
    app.dependency_overrides[get_storage] = lambda: storage
    content = b"Example agreement\n"
    metadata = {
        "mime_type": "text/plain",
        "file_size": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
    }
    upload_headers = {**headers, "Content-Type": "text/plain"}
    with TestClient(app) as client:
        document = client.post(
            "/api/v1/documents",
            json={"name": "Upload example", "document_type": "contract"},
            headers=headers,
        ).json()
        endpoint = f"/api/v1/documents/{document['id']}/versions"

        def register() -> tuple[str, str]:
            response = client.post(endpoint, json=metadata, headers=headers)
            assert response.status_code == 201
            assert response.json()["uploaded_at"] is None
            version_id = response.json()["id"]
            return version_id, f"{endpoint}/{version_id}/content"

        version_id, url = register()
        assert client.put(url, content=content).status_code == 401
        for bad in (content[:-1], content + b"extra", b"x" * len(content)):
            assert client.put(url, content=bad, headers=upload_headers).status_code == 422
        assert client.put(url, content=content, headers=headers).status_code == 422
        assert (
            client.put(
                url.replace(version_id, str(uuid4())), content=content, headers=upload_headers
            ).status_code
            == 404
        )
        assert storage.objects == {}
        storage.fail = True
        assert client.put(url, content=content, headers=upload_headers).status_code == 503
        assert client.get(endpoint, headers=headers).json()[0]["uploaded_at"] is None
        storage.fail = False

        def send() -> dict:
            response = client.put(url, content=content, headers=upload_headers)
            assert response.status_code == 200, response.text
            return response.json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))
        assert results[0] == results[1] == send()
        assert results[0]["uploaded_at"] is not None
        assert len(storage.objects) == 1
        assert "storage_key" not in results[0]

        async def verify() -> tuple[UUID, UUID]:
            db = Database(settings)
            try:
                async with db.sessions() as session:
                    version = await session.get(DocumentVersion, UUID(version_id))
                    assert version is not None
                    assert version.storage_key in storage.objects
                    assert version.storage_version_id == "s3-version-id"
                    assert version.storage_key.startswith(
                        f"tenants/{settings.development_tenant_id}/"
                    )
                    count = await session.scalar(
                        select(func.count())
                        .select_from(AuditLog)
                        .where(
                            AuditLog.resource_id == UUID(document["id"]),
                            AuditLog.action == "document.version_uploaded",
                        )
                    )
                    assert count == 1
                    member_id = await session.scalar(
                        select(User.id).where(User.email == "reader@example.com")
                    )
                    foreign_id = await session.scalar(
                        select(User.id).where(User.tenant_id == other_tenant)
                    )
                    assert member_id and foreign_id
                    version.storage_key = None
                    with pytest.raises(IntegrityError):
                        await session.commit()
                    await session.rollback()
                    foreign_role = await session.scalar(
                        select(Role.id).where(
                            Role.tenant_id == other_tenant, Role.name == "tenant_admin"
                        )
                    )
                    session.add(
                        UserRole(tenant_id=other_tenant, user_id=foreign_id, role_id=foreign_role)
                    )
                    await session.commit()
                    return member_id, foreign_id
            finally:
                await db.dispose()

        member_id, foreign_id = asyncio.run(verify())
        for user_id, tenant_id, status in (
            (member_id, settings.development_tenant_id, 403),
            (foreign_id, other_tenant, 404),
        ):
            scoped_app = create_app(
                settings.model_copy(
                    update={
                        "development_user_id": user_id,
                        "development_tenant_id": tenant_id,
                    }
                )
            )
            scoped_app.dependency_overrides[get_storage] = lambda: storage
            with TestClient(scoped_app) as scoped:
                assert (
                    scoped.put(url, content=content, headers=upload_headers).status_code == status
                )

        failed_id, failed_url = register()
        with (
            patch.object(
                AuditRepository,
                "record_document_event",
                AsyncMock(side_effect=RuntimeError("audit failure")),
            ),
            pytest.raises(RuntimeError, match="audit failure"),
        ):
            client.put(failed_url, content=content, headers=upload_headers)
        rows = client.get(endpoint, headers=headers).json()
        assert next(row for row in rows if row["id"] == failed_id)["uploaded_at"] is None
        assert len(storage.objects) == 2  # Private orphan retained on uncertain DB failures.
        assert client.put(failed_url, content=content, headers=upload_headers).status_code == 200
        assert len(storage.objects) == 3

    with TestClient(create_app(settings)) as unconfigured:
        assert unconfigured.put(url, content=content, headers=upload_headers).status_code == 503
