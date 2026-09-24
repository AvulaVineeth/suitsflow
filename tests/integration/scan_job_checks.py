import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from tests.integration.upload_checks import MemoryStorage, TestScanner

from suitsflow.api.routes.documents import get_storage
from suitsflow.db.models import DocumentScanJob, User
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.services.scan_jobs import ScanJobs


def exercise_scan_jobs(settings, other_tenant, headers):
    storage, scanner = MemoryStorage(), TestScanner()
    app = create_app(settings)
    app.dependency_overrides[get_storage] = lambda: storage

    async def run(concurrent=False):
        db = Database(settings)

        async def once():
            async with db.sessions() as session:
                return await ScanJobs(session).run_one(storage, scanner)

        try:
            return await asyncio.gather(once(), once()) if concurrent else await once()
        finally:
            await db.dispose()

    async def mutate(job_id, **values):
        db = Database(settings)
        try:
            async with db.sessions() as session:
                await session.execute(
                    update(DocumentScanJob)
                    .where(DocumentScanJob.id == UUID(job_id))
                    .values(**values)
                )
                await session.commit()
        finally:
            await db.dispose()

    async def actor_active(active):
        db = Database(settings)
        try:
            async with db.sessions() as session:
                await session.execute(
                    update(User)
                    .where(User.id == settings.development_user_id)
                    .values(status="active" if active else "disabled")
                )
                await session.commit()
        finally:
            await db.dispose()

    async def reader_id():
        db = Database(settings)
        try:
            async with db.sessions() as session:
                return await session.scalar(
                    select(User.id).where(
                        User.tenant_id == settings.development_tenant_id,
                        User.email == "reader@example.com",
                    )
                )
        finally:
            await db.dispose()

    with TestClient(app) as client:
        doc = client.post(
            "/api/v1/documents",
            headers=headers,
            json={"name": "Background scan", "document_type": "contract"},
        ).json()
        base = f"/api/v1/documents/{doc['id']}/versions"
        content = b"Queued agreement\n"

        def register():
            response = client.post(
                base,
                headers=headers,
                json={
                    "mime_type": "text/plain",
                    "file_size": len(content),
                    "checksum": hashlib.sha256(content).hexdigest(),
                },
            )
            assert response.status_code == 201
            return base + "/" + response.json()["id"]

        def upload(url):
            assert (
                client.put(
                    url + "/content",
                    content=content,
                    headers={**headers, "Content-Type": "text/plain"},
                ).status_code
                == 200
            )

        def queue(url):
            response = client.post(url + "/scan-job", headers=headers)
            assert response.status_code == 202
            return response.json()

        def state(url):
            response = client.get(url + "/scan-job", headers=headers)
            assert response.status_code == 200
            return response.json()

        url = register()
        assert client.post(url + "/scan-job").status_code == 401
        assert client.get(url + "/scan-job", headers=headers).status_code == 404
        assert client.post(url + "/scan-job", headers=headers).status_code == 409
        upload(url)
        job = queue(url)
        assert queue(url)["id"] == job["id"]
        assert job["status"] == "pending"
        assert not {"tenant_id", "claim_token", "requested_by", "lease_until"} & job.keys()
        member_settings = settings.model_copy(
            update={"development_user_id": asyncio.run(reader_id())}
        )
        with TestClient(create_app(member_settings)) as member:
            assert member.post(url + "/scan-job", headers=headers).status_code == 403
            assert member.get(url + "/scan-job", headers=headers).status_code == 200
        foreign_settings = settings.model_copy(update={"development_tenant_id": other_tenant})
        with TestClient(create_app(foreign_settings)) as foreign:
            assert foreign.get(url + "/scan-job", headers=headers).status_code == 403
        missing = url.replace(doc["id"], str(uuid4())) + "/scan-job"
        assert client.get(missing, headers=headers).status_code == 404
        assert client.post(missing, headers=headers).status_code == 404
        assert sorted(asyncio.run(run(concurrent=True))) == [False, True]
        assert scanner.calls == 1
        assert state(url)["status"] == "completed"
        assert client.get(url + "/content", headers=headers).status_code == 200
        assert queue(url)["status"] == "completed"
        assert asyncio.run(run()) is False

        url = register()
        upload(url)
        job = queue(url)
        scanner.verdict = "error"
        assert asyncio.run(run())
        assert state(url)["status"] == "failed"
        assert client.get(url + "/content", headers=headers).status_code == 409
        assert queue(url)["id"] == job["id"]
        scanner.verdict = "clean"
        assert asyncio.run(run())
        assert state(url)["attempts"] == 2
        assert state(url)["status"] == "completed"

        # A crashed claimant can be reclaimed; an obsolete claimant cannot publish.
        url = register()
        upload(url)
        job = queue(url)
        asyncio.run(
            mutate(
                job["id"],
                status="running",
                claim_token=uuid4(),
                lease_until=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        original_scan = scanner.scan

        def stale_scan(body):
            verdict = original_scan(body)
            asyncio.run(mutate(job["id"], claim_token=uuid4()))
            return verdict

        with patch.object(scanner, "scan", side_effect=stale_scan):
            assert asyncio.run(run())
        assert state(url)["status"] == "running"
        assert client.get(url + "/content", headers=headers).status_code == 409
        asyncio.run(mutate(job["id"], lease_until=datetime.now(UTC) - timedelta(seconds=1)))
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"

        # Audit failure must roll back both verdict and completion, preserving the lease.
        url = register()
        upload(url)
        job = queue(url)
        with (
            patch.object(
                AuditRepository,
                "record_document_event",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ),
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            asyncio.run(run())
        assert state(url)["status"] == "running"
        assert client.get(url + "/content", headers=headers).status_code == 409
        asyncio.run(mutate(job["id"], lease_until=datetime.now(UTC) - timedelta(seconds=1)))
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"

        # Recheck active membership at execution, before any storage/scanner I/O.
        url = register()
        upload(url)
        queue(url)
        before = scanner.calls
        asyncio.run(actor_active(False))
        try:
            assert asyncio.run(run())
        finally:
            asyncio.run(actor_active(True))
        assert scanner.calls == before
        assert state(url)["status"] == "failed"
        assert client.get(url + "/content", headers=headers).status_code == 409
        queue(url)
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"
