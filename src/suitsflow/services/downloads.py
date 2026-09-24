from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import Principal, ResourceNotFound, require_document_access
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.services.storage import ObjectStorage, StoredObject


class ContentNotUploaded(Exception):
    pass


class ContentNotCleared(Exception):
    pass


@dataclass(frozen=True)
class Download:
    body: BinaryIO
    size: int
    filename: str


class DownloadService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def download(self, principal: Principal, document_id: UUID, version_id: UUID) -> Download:
        require_document_access(principal)
        version = await self.repository.version(principal.tenant_id, document_id, version_id)
        if version is None:
            raise ResourceNotFound
        if (
            version.uploaded_at is None
            or version.storage_bucket is None
            or version.storage_key is None
        ):
            raise ContentNotUploaded
        if version.content_status != "clean":
            raise ContentNotCleared
        reference = StoredObject(
            version.storage_bucket, version.storage_key, version.storage_version_id
        )
        size, checksum = version.file_size, version.checksum
        extension = {"application/pdf": "pdf", "text/plain": "txt"}.get(version.mime_type, "docx")
        filename = f"{document_id}-v{version.version_number}.{extension}"
        await self.repository.session.rollback()
        body = cast(BinaryIO, SpooledTemporaryFile[bytes](max_size=2 * 1024 * 1024, mode="w+b"))
        try:
            await run_in_threadpool(
                self.storage.download, reference, body, size=size, checksum=checksum
            )
            return Download(body, size, filename)
        except BaseException:
            body.close()
            raise
