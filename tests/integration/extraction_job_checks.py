import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.integration.upload_checks import MemoryStorage, TestScanner

from suitsflow.api.routes.documents import get_scanner, get_storage
from suitsflow.db.models import DocumentExtractionJob, User
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.services.extraction import ExtractionService
from suitsflow.services.extraction_jobs import ExtractionJobs


def exercise_extraction_jobs(settings, other_tenant, headers):
    storage, scanner = MemoryStorage(), TestScanner()
    app = create_app(settings)
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_scanner] = lambda: scanner

    async def run(concurrent=False):
        db = Database(settings)

        async def once():
            async with db.sessions() as session:
                return await ExtractionJobs(session).run_one(storage)

        try:
            return await asyncio.gather(once(), once()) if concurrent else await once()
        finally:
            await db.dispose()

    async def mutate(job_id, **values):
        db = Database(settings)
        try:
            async with db.sessions() as session:
                await session.execute(
                    update(DocumentExtractionJob)
                    .where(DocumentExtractionJob.id == UUID(job_id))
                    .values(**values)
                )
                await session.commit()
        finally:
            await db.dispose()

    async def actor_status(status):
        db = Database(settings)
        try:
            async with db.sessions() as session:
                await session.execute(
                    update(User)
                    .where(User.id == settings.development_user_id)
                    .values(status=status)
                )
                await session.commit()
        finally:
            await db.dispose()

    async def identities():
        db = Database(settings)
        try:
            async with db.sessions() as session:
                member = await session.scalar(
                    select(User.id).where(
                        User.tenant_id == settings.development_tenant_id,
                        User.email == "reader@example.com",
                    )
                )
                foreign = await session.scalar(
                    select(User.id).where(User.tenant_id == other_tenant)
                )
                return member, foreign
        finally:
            await db.dispose()

    with TestClient(app) as client:
        doc = client.post(
            "/api/v1/documents",
            headers=headers,
            json={"name": "Queued extraction", "document_type": "contract"},
        ).json()
        base = f"/api/v1/documents/{doc['id']}/versions"
        content = b"Queued contract terms\n"

        def upload(clear=True):
            version = client.post(
                base,
                headers=headers,
                json={
                    "mime_type": "text/plain",
                    "file_size": len(content),
                    "checksum": hashlib.sha256(content).hexdigest(),
                },
            ).json()
            url = base + "/" + version["id"]
            assert (
                client.put(
                    url + "/content",
                    content=content,
                    headers={**headers, "Content-Type": "text/plain"},
                ).status_code
                == 200
            )
            if clear:
                assert client.post(url + "/scan", headers=headers).status_code == 200
            return url

        def queue(url):
            result = client.post(url + "/extraction-job", headers=headers)
            assert result.status_code == 202
            return result.json()

        def state(url):
            result = client.get(url + "/extraction-job", headers=headers)
            assert result.status_code == 200
            return result.json()

        def expire(job):
            asyncio.run(mutate(job["id"], lease_until=datetime.now(UTC) - timedelta(seconds=1)))

        url = upload(clear=False)
        assert client.post(url + "/extraction-job", headers=headers).status_code == 409
        assert client.post(url + "/scan", headers=headers).status_code == 200
        assert client.get(url + "/extraction-job", headers=headers).status_code == 404
        assert client.post(url + "/extraction-job").status_code == 401
        job = queue(url)
        assert queue(url)["id"] == job["id"]
        assert job["result_id"] is None
        assert job["extractor"] == "plain-text-v1"
        assert not {"tenant_id", "claim_token", "requested_by", "lease_until"} & job.keys()
        member_id, foreign_id = asyncio.run(identities())
        for user_id, tenant_id, write_code, read_code in (
            (member_id, settings.development_tenant_id, 403, 200),
            (foreign_id, other_tenant, 404, 404),
        ):
            with TestClient(
                create_app(
                    settings.model_copy(
                        update={"development_user_id": user_id, "development_tenant_id": tenant_id}
                    )
                )
            ) as scoped:
                assert (
                    scoped.post(url + "/extraction-job", headers=headers).status_code == write_code
                )
                assert scoped.get(url + "/extraction-job", headers=headers).status_code == read_code
        assert sorted(asyncio.run(run(concurrent=True))) == [False, True]
        result = client.get(url + "/extraction", headers=headers).json()
        assert state(url)["status"] == "completed"
        assert state(url)["result_id"] == result["id"]
        assert queue(url)["status"] == "completed"
        assert asyncio.run(run()) is False

        url = upload()
        job = queue(url)
        storage.fail = True
        assert asyncio.run(run())
        storage.fail = False
        assert state(url)["status"] == "failed"
        assert state(url)["result_id"] is None
        assert queue(url)["id"] == job["id"]
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"
        assert state(url)["attempts"] == 2

        url = upload()
        job = queue(url)
        original_put = storage.put

        def stale_put(*args, **kwargs):
            reference = original_put(*args, **kwargs)
            asyncio.run(mutate(job["id"], claim_token=uuid4()))
            return reference

        with patch.object(storage, "put", side_effect=stale_put):
            assert asyncio.run(run())
        assert state(url)["status"] == "running"
        assert client.get(url + "/extraction", headers=headers).status_code == 404
        expire(job)
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"

        url = upload()
        job = queue(url)
        original_audit = AuditRepository.record_document_event

        async def fail_completion(repository, *args, **kwargs):
            if kwargs["action"] == "document.version_extraction_completed":
                raise RuntimeError("completion audit failed")
            await original_audit(repository, *args, **kwargs)

        with (
            patch.object(AuditRepository, "record_document_event", new=fail_completion),
            pytest.raises(RuntimeError, match="completion audit failed"),
        ):
            asyncio.run(run())
        assert state(url)["status"] == "running"
        assert client.get(url + "/extraction", headers=headers).status_code == 404
        expire(job)
        assert asyncio.run(run())
        assert state(url)["status"] == "completed"

        url = upload()
        saved = client.post(url + "/extraction", headers=headers).json()
        queue(url)
        with patch.object(
            ExtractionService,
            "extract",
            new=AsyncMock(side_effect=AssertionError("must reuse artifact")),
        ):
            assert asyncio.run(run())
        assert state(url)["result_id"] == saved["id"]

        url = upload()
        job = queue(url)
        asyncio.run(actor_status("disabled"))
        try:
            with patch.object(
                storage, "download", side_effect=AssertionError("no unauthorized I/O")
            ):
                assert asyncio.run(run())
        finally:
            asyncio.run(actor_status("active"))
        assert state(url)["status"] == "failed"
        assert client.get(url + "/extraction", headers=headers).status_code == 404
        with pytest.raises(IntegrityError):
            asyncio.run(mutate(job["id"], status="completed", result_id=UUID(saved["id"])))
        assert state(url)["status"] == "failed"
