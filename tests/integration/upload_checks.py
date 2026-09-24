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

from suitsflow.api.routes.documents import get_scanner, get_storage
from suitsflow.core.config import Settings
from suitsflow.db.models import AuditLog, DocumentVersion, Role, User, UserRole
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.services.scanner import ScannerUnavailable
from suitsflow.services.storage import StorageUnavailable, StoredObject


class TestScanner:
    def __init__(self):
        self.verdict = "clean"
        self.calls = 0

    def scan(self, body):
        self.calls += 1
        assert body.read()
        if self.verdict == "error":
            raise ScannerUnavailable
        return self.verdict


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False

    def download(
        self, reference: StoredObject, target: BinaryIO, *, size: int, checksum: str
    ) -> None:
        if self.fail or reference.key not in self.objects:
            raise StorageUnavailable
        assert reference.bucket == "private-test"
        assert reference.version_id == "s3-version-id"
        target.write(self.objects[reference.key])
        target.seek(0)

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
    scanner = TestScanner()
    app.dependency_overrides[get_scanner] = lambda: scanner
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
        assert client.get(url).status_code == 401
        assert client.get(url, headers=headers).status_code == 409
        assert client.get(url.replace(version_id, str(uuid4())), headers=headers).status_code == 404
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
        assert client.get(url, headers=headers).status_code == 409
        scan_url = url.removesuffix("content") + "scan"
        with ThreadPoolExecutor(max_workers=2) as pool:
            scan_responses = list(
                pool.map(lambda _: client.post(scan_url, headers=headers), range(2))
            )
        assert all(response.status_code == 200 for response in scan_responses)
        assert scan_responses[0].json()["content_status"] == "clean"
        assert scanner.calls == 1
        downloaded = client.get(url, headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["cache-control"] == "no-store"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert downloaded.headers["content-length"] == str(len(content))
        storage.fail = True
        assert client.get(url, headers=headers).status_code == 503
        storage.fail = False

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
            scoped_app.dependency_overrides[get_scanner] = lambda: scanner
            with TestClient(scoped_app) as scoped:
                assert scoped.post(scan_url, headers=headers).status_code == status
                download = scoped.get(url, headers=headers)
                assert download.status_code == (200 if user_id == member_id else 404)
                if user_id == member_id:
                    assert download.content == content
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
        retry_scan_url = failed_url.removesuffix("content") + "scan"
        scanner.verdict = "error"
        assert (
            client.post(retry_scan_url, headers=headers).json()["content_status"] == "scan_failed"
        )
        assert client.get(failed_url, headers=headers).status_code == 409
        scanner.verdict = "rejected"
        assert client.post(retry_scan_url, headers=headers).json()["content_status"] == "rejected"
        scanner.verdict = "clean"
        assert client.post(retry_scan_url, headers=headers).json()["content_status"] == "rejected"
        assert client.get(failed_url, headers=headers).status_code == 409
        _, pending_url = register()
        pending_scan = pending_url.removesuffix("content") + "scan"
        assert client.post(pending_scan, headers=headers).status_code == 409
        assert client.put(pending_url, content=content, headers=upload_headers).status_code == 200
        with (
            patch.object(
                AuditRepository,
                "record_document_event",
                AsyncMock(side_effect=RuntimeError("scan audit failure")),
            ),
            pytest.raises(RuntimeError, match="scan audit failure"),
        ):
            client.post(pending_scan, headers=headers)
        assert client.get(pending_url, headers=headers).status_code == 409
        assert client.post(pending_scan, headers=headers).json()["content_status"] == "clean"
        app.dependency_overrides.pop(get_scanner)
        assert client.post(pending_scan, headers=headers).status_code == 503

    with TestClient(create_app(settings)) as unconfigured:
        assert unconfigured.put(url, content=content, headers=upload_headers).status_code == 503
