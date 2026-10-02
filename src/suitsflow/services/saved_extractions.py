import hashlib
from io import BytesIO
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import (
    AccessDenied,
    Identity,
    Principal,
    ResourceNotFound,
    require_document_access,
)
from suitsflow.db.models import DocumentExtraction, DocumentVersion
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.repositories.memberships import MembershipRepository
from suitsflow.schemas.extraction import SavedExtractionResponse
from suitsflow.services.downloads import ContentNotCleared
from suitsflow.services.extraction import ExtractionService, InvalidTextContent, extractor_for
from suitsflow.services.storage import ObjectStorage, StorageUnavailable, StoredObject


class SavedExtractions:
    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository
        self.session = repository.session

    async def _existing(self, version: DocumentVersion) -> DocumentExtraction | None:
        return cast(
            DocumentExtraction | None,
            await self.session.scalar(
                select(DocumentExtraction).where(
                    DocumentExtraction.tenant_id == version.tenant_id,
                    DocumentExtraction.version_id == version.id,
                    DocumentExtraction.extractor == extractor_for(version.mime_type),
                )
            ),
        )

    async def _read(
        self, version: DocumentVersion, record: DocumentExtraction, storage: ObjectStorage
    ) -> SavedExtractionResponse:
        response = SavedExtractionResponse(
            id=record.id,
            document_id=version.document_id,
            version_id=version.id,
            version_number=version.version_number,
            source_checksum=record.source_checksum,
            extractor=extractor_for(version.mime_type),
            text="",
            character_count=record.character_count,
            text_checksum=record.text_checksum,
            created_at=record.created_at,
        )
        reference = StoredObject(
            record.storage_bucket, record.storage_key, record.storage_version_id
        )
        size, checksum = record.text_bytes, record.text_checksum
        await self.session.rollback()
        with BytesIO() as target:
            await run_in_threadpool(
                storage.download, reference, target, size=size, checksum=checksum
            )
            content = target.read(4_000_001)
        if len(content) != size or hashlib.sha256(content).hexdigest() != checksum:
            raise StorageUnavailable
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StorageUnavailable from exc
        if len(text) != response.character_count:
            raise StorageUnavailable
        return response.model_copy(update={"text": text})

    async def get(
        self, principal: Principal, document_id: UUID, version_id: UUID, storage: ObjectStorage
    ) -> SavedExtractionResponse:
        require_document_access(principal)
        version = await self.repository.version(principal.tenant_id, document_id, version_id)
        if version is None:
            raise ResourceNotFound
        if version.content_status != "clean":
            raise ContentNotCleared
        record = await self._existing(version)
        if record is None:
            raise ResourceNotFound
        return await self._read(version, record, storage)

    async def save(
        self, principal: Principal, document_id: UUID, version_id: UUID, storage: ObjectStorage
    ) -> SavedExtractionResponse:
        require_document_access(principal, write=True)
        try:
            try:
                response = await self.get(principal, document_id, version_id, storage)
            except ResourceNotFound:
                pass
            else:
                await self.session.rollback()
                return response
            # Parsing performs verified I/O after releasing its read transaction.
            extracted = await ExtractionService(self.repository, storage).extract(
                principal, document_id, version_id
            )
            if "\x00" in extracted.text:
                raise InvalidTextContent
            artifact_id = uuid4()
            content = extracted.text.encode("utf-8")
            checksum = hashlib.sha256(content).hexdigest()
            key = f"tenants/{principal.tenant_id}/extractions/{version_id}/{artifact_id}.txt"
            with BytesIO(content) as body:
                reference = await run_in_threadpool(
                    storage.put,
                    key,
                    body,
                    size=len(content),
                    checksum=checksum,
                    mime_type="text/plain",
                )
            version = await self.repository.version(
                principal.tenant_id, document_id, version_id, lock=True
            )
            if version is None:
                raise ResourceNotFound
            if version.content_status != "clean" or version.checksum != extracted.source_checksum:
                raise ContentNotCleared
            current = await MembershipRepository(self.session).get_principal(
                Identity(principal.user_id, principal.tenant_id)
            )
            if current is None:
                raise AccessDenied
            require_document_access(current, write=True)
            record = await self._existing(version)
            if record is None:
                record = DocumentExtraction(
                    id=artifact_id,
                    tenant_id=principal.tenant_id,
                    version_id=version_id,
                    source_checksum=extracted.source_checksum,
                    extractor=extracted.extractor,
                    storage_bucket=reference.bucket,
                    storage_key=reference.key,
                    storage_version_id=reference.version_id,
                    text_bytes=len(content),
                    character_count=extracted.character_count,
                    text_checksum=checksum,
                    created_by=principal.user_id,
                )
                self.session.add(record)
                await self.session.flush()
                await AuditRepository(self.session).record_document_event(
                    current,
                    document_id,
                    action="document.version_extraction_saved",
                    version_number=version.version_number,
                )
            await self.session.commit()
            return await self._read(version, record, storage)
        except BaseException:
            await self.session.rollback()
            raise
