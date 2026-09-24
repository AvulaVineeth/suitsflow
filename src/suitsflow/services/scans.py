from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import Principal, ResourceNotFound, require_document_access
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.document import VersionResponse
from suitsflow.services.downloads import ContentNotUploaded
from suitsflow.services.scanner import Scanner, ScannerUnavailable
from suitsflow.services.storage import ObjectStorage, StorageUnavailable, StoredObject


class ScanService:
    def __init__(
        self, repository: DocumentRepository, storage: ObjectStorage, scanner: Scanner
    ) -> None:
        self.repository, self.storage, self.scanner = repository, storage, scanner

    async def scan(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> VersionResponse:
        require_document_access(principal, write=True)
        session = self.repository.session
        try:
            version = await self.repository.version(
                principal.tenant_id, document_id, version_id, lock=True
            )
            if version is None:
                raise ResourceNotFound
            if (
                version.uploaded_at is None
                or version.storage_bucket is None
                or version.storage_key is None
            ):
                raise ContentNotUploaded
            if version.content_status in {"clean", "rejected"}:
                response = VersionResponse.model_validate(version)
                await session.rollback()
                return response
            reference = StoredObject(
                version.storage_bucket, version.storage_key, version.storage_version_id
            )
            with SpooledTemporaryFile[bytes](max_size=2 * 1024 * 1024, mode="w+b") as body:
                file = cast(BinaryIO, body)
                try:
                    await run_in_threadpool(
                        self.storage.download,
                        reference,
                        file,
                        size=version.file_size,
                        checksum=version.checksum,
                    )
                    verdict = await run_in_threadpool(self.scanner.scan, file)
                    if verdict not in {"clean", "rejected"}:
                        raise ScannerUnavailable
                    version.content_status = verdict
                except (StorageUnavailable, ScannerUnavailable):
                    version.content_status = "scan_failed"
            version.scanned_at = datetime.now(UTC)
            await session.flush()
            await AuditRepository(session).record_document_event(
                principal,
                document_id,
                action=f"document.version_scan_{version.content_status}",
                version_number=version.version_number,
            )
            response = VersionResponse.model_validate(version)
            await session.commit()
            return response
        except BaseException:
            await session.rollback()
            raise
