from datetime import UTC, datetime, timedelta
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from suitsflow.core.security import Identity, Principal, ResourceNotFound, require_document_access
from suitsflow.db.models import DocumentScanJob, DocumentVersion
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.repositories.memberships import MembershipRepository
from suitsflow.schemas.scan_job import ScanJobResponse
from suitsflow.services.downloads import ContentNotUploaded
from suitsflow.services.scanner import Scanner, ScannerUnavailable
from suitsflow.services.storage import ObjectStorage, StorageUnavailable, StoredObject


class ScanJobs:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> ScanJobResponse:
        require_document_access(principal, write=True)
        try:
            version = await DocumentRepository(self.session).version(
                principal.tenant_id, document_id, version_id, lock=True
            )
            if version is None:
                raise ResourceNotFound
            if version.uploaded_at is None:
                raise ContentNotUploaded
            job = await self.session.scalar(
                select(DocumentScanJob)
                .where(
                    DocumentScanJob.tenant_id == principal.tenant_id,
                    DocumentScanJob.version_id == version_id,
                )
                .with_for_update()
            )
            if job is None:
                job = DocumentScanJob(
                    tenant_id=principal.tenant_id,
                    version_id=version_id,
                    requested_by=principal.user_id,
                )
                self.session.add(job)
            elif job.status != "failed":
                result = ScanJobResponse.model_validate(job)
                await self.session.rollback()
                return result
            else:
                job.status = "pending"
                job.requested_by = principal.user_id
            await self.session.flush()
            await self.session.refresh(job)
            await AuditRepository(self.session).record_document_event(
                principal,
                document_id,
                action="document.version_scan_queued",
                version_number=version.version_number,
            )
            result = ScanJobResponse.model_validate(job)
            await self.session.commit()
            return result
        except BaseException:
            await self.session.rollback()
            raise

    async def get(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> ScanJobResponse:
        require_document_access(principal)
        if (
            await DocumentRepository(self.session).version(
                principal.tenant_id, document_id, version_id
            )
            is None
        ):
            raise ResourceNotFound
        job = await self.session.scalar(
            select(DocumentScanJob).where(
                DocumentScanJob.tenant_id == principal.tenant_id,
                DocumentScanJob.version_id == version_id,
            )
        )
        if job is None:
            raise ResourceNotFound
        return ScanJobResponse.model_validate(job)

    async def run_one(self, storage: ObjectStorage, scanner: Scanner) -> bool:
        """Claim in a short transaction; no database lock is held during external I/O."""
        job = await self.session.scalar(
            select(DocumentScanJob)
            .where(
                or_(
                    DocumentScanJob.status == "pending",
                    (DocumentScanJob.status == "running")
                    & (DocumentScanJob.lease_until < datetime.now(UTC)),
                )
            )
            .order_by(DocumentScanJob.created_at, DocumentScanJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            await self.session.rollback()
            return False
        job.status, job.claim_token = "running", uuid4()
        job.lease_until = datetime.now(UTC) + timedelta(minutes=15)
        job.attempts += 1
        job_id, token, tenant_id, version_id, actor = (
            job.id,
            job.claim_token,
            job.tenant_id,
            job.version_id,
            job.requested_by,
        )
        await self.session.commit()
        identity = Identity(actor, tenant_id)
        principal = await MembershipRepository(self.session).get_principal(identity)
        version = await self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.tenant_id == tenant_id, DocumentVersion.id == version_id
            )
        )
        assert version is not None  # Protected by the composite foreign key.
        reference = StoredObject(
            version.storage_bucket or "", version.storage_key or "", version.storage_version_id
        )
        size, checksum, document_id, status = (
            version.file_size,
            version.checksum,
            version.document_id,
            version.content_status,
        )
        await self.session.rollback()
        permitted = principal is not None and "tenant_admin" in principal.roles
        verdict = "scan_failed"
        if permitted and status not in {"clean", "rejected"}:
            with SpooledTemporaryFile[bytes](max_size=2 * 1024 * 1024, mode="w+b") as body:
                file = cast(BinaryIO, body)
                try:
                    await run_in_threadpool(
                        storage.download, reference, file, size=size, checksum=checksum
                    )
                    verdict = await run_in_threadpool(scanner.scan, file)
                    if verdict not in {"clean", "rejected"}:
                        verdict = "scan_failed"
                except (StorageUnavailable, ScannerUnavailable):
                    verdict = "scan_failed"
        # Consistent lock order with enqueue: version first, then job.
        version = await DocumentRepository(self.session).version(
            tenant_id, document_id, version_id, lock=True
        )
        job = await self.session.scalar(
            select(DocumentScanJob)
            .where(DocumentScanJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            job is None
            or job.claim_token != token
            or job.lease_until is None
            or job.lease_until <= datetime.now(UTC)
        ):
            await self.session.rollback()
            return True  # An expired/stale worker cannot publish its result.
        current = await MembershipRepository(self.session).get_principal(identity)
        permitted = permitted and current is not None and "tenant_admin" in current.roles
        assert version is not None
        if permitted and version.content_status not in {"clean", "rejected"}:
            version.content_status, version.scanned_at = verdict, datetime.now(UTC)
            await AuditRepository(self.session).record_document_event(
                cast(Principal, current),
                document_id,
                action=f"document.version_scan_{verdict}",
                version_number=version.version_number,
            )
        job.status = (
            "completed"
            if permitted and version.content_status in {"clean", "rejected"}
            else "failed"
        )
        job.claim_token, job.lease_until = None, None
        await self.session.commit()
        return True
