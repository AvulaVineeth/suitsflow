import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast
from uuid import UUID, uuid4

from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import (
    AccessDenied,
    Identity,
    Principal,
    ResourceNotFound,
    require_document_access,
)
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.repositories.memberships import MembershipRepository
from suitsflow.schemas.document import VersionResponse
from suitsflow.services.storage import ObjectStorage
from suitsflow.services.upload_validation import InvalidUpload, validate_format

logger = logging.getLogger(__name__)


class UploadService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def upload(
        self,
        principal: Principal,
        document_id: UUID,
        version_id: UUID,
        chunks: AsyncIterator[bytes],
        content_type: str,
        timeout: float,
    ) -> VersionResponse:
        require_document_access(principal, write=True)
        session = self.repository.session
        version = await self.repository.version(principal.tenant_id, document_id, version_id)
        if version is None:
            raise ResourceNotFound
        size, checksum, mime_type = version.file_size, version.checksum, version.mime_type
        if content_type.strip().lower() != mime_type:
            raise InvalidUpload("Content-Type must match the registered MIME type")
        # Release the connection while the request body arrives. Re-lock after validation.
        await session.rollback()
        with SpooledTemporaryFile[bytes](max_size=2 * 1024 * 1024, mode="w+b") as body:
            file = cast(BinaryIO, body)
            digest, received = hashlib.sha256(), 0
            async with asyncio.timeout(timeout):
                async for chunk in chunks:
                    received += len(chunk)
                    if received > size:
                        raise InvalidUpload("File exceeds the registered size")
                    digest.update(chunk)
                    await run_in_threadpool(body.write, chunk)
            if received != size or digest.hexdigest() != checksum:
                raise InvalidUpload("File size or SHA-256 does not match the registered metadata")
            await run_in_threadpool(validate_format, file, mime_type)
            try:
                version = await self.repository.version(
                    principal.tenant_id, document_id, version_id, lock=True
                )
                if version is None:
                    raise ResourceNotFound
                current = await MembershipRepository(session).get_principal(
                    Identity(principal.user_id, principal.tenant_id)
                )
                if current is None:
                    raise AccessDenied
                require_document_access(current, write=True)
                if version.uploaded_at is not None:
                    response = VersionResponse.model_validate(version)
                    await session.rollback()
                    return response
                key = (
                    f"tenants/{principal.tenant_id}/documents/{document_id}/{version_id}/{uuid4()}"
                )
                stored = await run_in_threadpool(
                    self.storage.put, key, file, size=size, checksum=checksum, mime_type=mime_type
                )
                version.storage_bucket = stored.bucket
                version.storage_key = stored.key
                version.storage_version_id = stored.version_id
                version.uploaded_at = datetime.now(UTC)
                await session.flush()
                await AuditRepository(session).record_document_event(
                    principal,
                    document_id,
                    action="document.version_uploaded",
                    version_number=version.version_number,
                )
                response = VersionResponse.model_validate(version)
                await session.commit()
                return response
            except BaseException:
                # Never delete here: a lost commit acknowledgement could mean the DB
                # already references the object. Failed attempts can leave private orphans.
                logger.warning("Document upload did not finish normally: version=%s", version_id)
                await session.rollback()
                raise
