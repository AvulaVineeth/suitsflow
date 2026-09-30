import asyncio
import hashlib
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.integration.upload_checks import MemoryStorage, TestScanner
from tests.test_docx_text import document, docx
from tests.test_pdf_text import pdf

from suitsflow.api.routes.documents import get_scanner, get_storage
from suitsflow.db.models import User
from suitsflow.db.session import Database
from suitsflow.main import create_app
from suitsflow.services.docx_text import DOCX_MIME


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
        member_settings = settings.model_copy(update={"development_user_id": member_id})
        with TestClient(app_for(member_settings)) as member:
            assert member.get(url + "/text", headers=headers).status_code == 200
        foreign_settings = settings.model_copy(
            update={"development_user_id": foreign_id, "development_tenant_id": other_tenant}
        )
        with TestClient(app_for(foreign_settings)) as foreign:
            assert foreign.get(url + "/text", headers=headers).status_code == 404
        assert (
            client.get(
                url.replace(version["id"], str(uuid4())) + "/text", headers=headers
            ).status_code
            == 404
        )
        storage.fail = True
        assert client.get(url + "/text", headers=headers).status_code == 503
        storage.fail = False

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
