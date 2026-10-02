import asyncio
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.integration.upload_checks import MemoryStorage, TestScanner
from tests.test_docx_text import document, docx
from tests.test_pdf_text import pdf

from suitsflow.api.routes.documents import get_scanner, get_storage
from suitsflow.db.models import AuditLog, DocumentExtraction, User
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.repositories.audit import AuditRepository
from suitsflow.services.docx_text import DOCX_MIME
from suitsflow.services.extraction import ExtractionService


def exercise_extraction(settings, other_tenant, headers):
    storage, scanner = MemoryStorage(), TestScanner()

    def app_for(config):
        app = create_app(config)
        app.dependency_overrides[get_storage] = lambda: storage
        app.dependency_overrides[get_scanner] = lambda: scanner
        return app

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

    member_id, foreign_id = asyncio.run(identities())
    with TestClient(app_for(settings)) as client:
        doc = client.post(
            "/api/v1/documents",
            headers=headers,
            json={"name": "Extraction", "document_type": "contract"},
        ).json()
        base = f"/api/v1/documents/{doc['id']}/versions"

        def upload(content, mime="text/plain"):
            version = client.post(
                base,
                headers=headers,
                json={
                    "mime_type": mime,
                    "file_size": len(content),
                    "checksum": hashlib.sha256(content).hexdigest(),
                },
            ).json()
            url = base + "/" + version["id"]
            assert (
                client.put(
                    url + "/content", content=content, headers={**headers, "Content-Type": mime}
                ).status_code
                == 200
            )
            return url, version

        def clear(url):
            assert client.post(url + "/scan", headers=headers).status_code == 200

        content = "Contract café\r\n<script>untrusted</script>".encode()
        url, version = upload(content)
        assert client.get(url + "/text").status_code == 401
        assert client.get(url + "/text", headers=headers).status_code == 409
        clear(url)
        response = client.get(url + "/text", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {
            "document_id": doc["id"],
            "version_id": version["id"],
            "version_number": version["version_number"],
            "source_checksum": version["checksum"],
            "extractor": "plain-text-v1",
            "text": content.decode(),
            "character_count": len(content.decode()),
        }
        saved_url = url + "/extraction"
        assert client.get(saved_url, headers=headers).status_code == 404
        assert client.post(saved_url).status_code == 401
        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(lambda _: client.post(saved_url, headers=headers), range(2)))
        assert all(result.status_code == 200 for result in saved)
        artifact = saved[0].json()
        assert artifact == saved[1].json()
        assert artifact["text_checksum"] == hashlib.sha256(content).hexdigest()
        assert artifact["source_checksum"] == version["checksum"]
        assert client.get(saved_url, headers=headers).json() == artifact
        assert client.get(saved_url, headers=headers).headers["cache-control"] == "no-store"

        async def verify_artifact_integrity():
            db = Database(settings)
            try:
                async with db.sessions() as session:
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(DocumentExtraction)
                            .where(DocumentExtraction.version_id == UUID(version["id"]))
                        )
                        == 1
                    )
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(AuditLog)
                            .where(
                                AuditLog.resource_id == UUID(doc["id"]),
                                AuditLog.action == "document.version_extraction_saved",
                            )
                        )
                        == 1
                    )
                    for query in (
                        "UPDATE document_extractions SET character_count = character_count",
                        "DELETE FROM document_extractions",
                        "TRUNCATE document_extractions",
                    ):
                        with pytest.raises(DBAPIError):
                            await session.execute(text(query))
                        await session.rollback()
                    session.add(
                        DocumentExtraction(
                            tenant_id=settings.development_tenant_id,
                            version_id=UUID(version["id"]),
                            source_checksum="0" * 64,
                            extractor="docx-body-v1",
                            storage_bucket="private-test",
                            storage_key="unused",
                            text_bytes=4,
                            character_count=4,
                            text_checksum="a" * 64,
                            created_by=settings.development_user_id,
                        )
                    )
                    with pytest.raises(IntegrityError, match="document_versions"):
                        await session.commit()
                    await session.rollback()
            finally:
                await db.dispose()

        asyncio.run(verify_artifact_integrity())
        member_settings = settings.model_copy(update={"development_user_id": member_id})
        with TestClient(app_for(member_settings)) as member:
            assert member.get(url + "/text", headers=headers).status_code == 200
            assert member.get(saved_url, headers=headers).json() == artifact
            assert member.post(saved_url, headers=headers).status_code == 403
        foreign_settings = settings.model_copy(
            update={"development_user_id": foreign_id, "development_tenant_id": other_tenant}
        )
        with TestClient(app_for(foreign_settings)) as foreign:
            assert foreign.get(url + "/text", headers=headers).status_code == 404
            assert foreign.get(saved_url, headers=headers).status_code == 404
            assert foreign.post(saved_url, headers=headers).status_code == 404
        assert (
            client.get(
                url.replace(version["id"], str(uuid4())) + "/text", headers=headers
            ).status_code
            == 404
        )
        storage.fail = True
        assert client.get(url + "/text", headers=headers).status_code == 503
        assert client.get(saved_url, headers=headers).status_code == 503
        assert client.post(saved_url, headers=headers).status_code == 503
        storage.fail = False
        with patch.object(
            ExtractionService,
            "extract",
            new=AsyncMock(side_effect=AssertionError("must reuse artifact")),
        ):
            assert client.get(saved_url, headers=headers).json() == artifact
            assert client.post(saved_url, headers=headers).json() == artifact
        artifact_key = next(key for key in storage.objects if artifact["id"] in key)
        original_bytes = storage.objects[artifact_key]
        storage.objects[artifact_key] = b"corrupted stored extraction"
        try:
            assert client.get(saved_url, headers=headers).status_code == 503
        finally:
            storage.objects[artifact_key] = original_bytes

        audit_url, _ = upload(b"Atomic saved extraction")
        assert client.post(audit_url + "/extraction", headers=headers).status_code == 409
        clear(audit_url)
        with (
            patch.object(
                AuditRepository,
                "record_document_event",
                new=AsyncMock(side_effect=RuntimeError("audit failed")),
            ),
            pytest.raises(RuntimeError, match="audit failed"),
        ):
            client.post(audit_url + "/extraction", headers=headers)
        assert client.get(audit_url + "/extraction", headers=headers).status_code == 404
        assert client.post(audit_url + "/extraction", headers=headers).status_code == 200

        # Permissions may change while parsing runs outside the transaction.
        revoked_url, _ = upload(b"Recheck permissions before publishing")
        clear(revoked_url)
        original_extract = ExtractionService.extract

        async def actor_status(status):
            db = Database(settings)
            try:
                async with db.sessions() as session:
                    actor = await session.get(User, settings.development_user_id)
                    actor.status = status
                    await session.commit()
            finally:
                await db.dispose()

        async def revoke_during_parse(service, *args):
            result = await original_extract(service, *args)
            await actor_status("disabled")
            return result

        try:
            with patch.object(ExtractionService, "extract", new=revoke_during_parse):
                assert client.post(revoked_url + "/extraction", headers=headers).status_code == 403
        finally:
            asyncio.run(actor_status("active"))
        assert client.get(revoked_url + "/extraction", headers=headers).status_code == 404

        url, _ = upload(b"invalid\x1btext")
        clear(url)
        assert client.get(url + "/text", headers=headers).status_code == 422
        if sys.platform == "linux":
            pdf_url, pdf_version = upload(pdf(), "application/pdf")
            assert client.get(pdf_url + "/text", headers=headers).status_code == 409
            clear(pdf_url)
            extracted = client.get(pdf_url + "/text", headers=headers)
            assert extracted.status_code == 200
            assert extracted.json()["extractor"] == "pdf-text-v1"
            assert "Contract terms" in extracted.json()["text"]
            assert extracted.json()["source_checksum"] == pdf_version["checksum"]
        url, _ = upload(b"a" * 1_000_001)
        clear(url)
        assert client.get(url + "/text", headers=headers).status_code == 413
        url, _ = upload(b"%PDF-1.4\n", "application/pdf")
        clear(url)
        assert client.get(url + "/text", headers=headers).status_code == (
            422 if sys.platform == "linux" else 503
        )
        url, version = upload(
            docx(document("<w:p><w:r><w:t>Contract terms</w:t></w:r></w:p>")), DOCX_MIME
        )
        assert client.get(url + "/text", headers=headers).status_code == 409
        clear(url)
        result = client.get(url + "/text", headers=headers)
        assert result.status_code == 200
        assert result.json()["extractor"] == "docx-body-v1"
        assert result.json()["text"] == "Contract terms\n"
        assert result.json()["source_checksum"] == version["checksum"]
        url, _ = upload(docx(document("<w:del/>")), DOCX_MIME)
        clear(url)
        assert client.get(url + "/text", headers=headers).status_code == 422
