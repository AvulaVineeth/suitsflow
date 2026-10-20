from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.core.security import (
    AccessDenied,
    Identity,
    Principal,
    ResourceNotFound,
    require_document_access,
)
from suitsflow.db.models import DocumentExtractionJob, DocumentVersion
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.repositories.memberships import MembershipRepository
from suitsflow.schemas.extraction_job import ExtractionJobResponse
from suitsflow.services.downloads import ContentNotCleared, ContentNotUploaded
from suitsflow.services.extraction import (
    ExtractionTooLarge,
    InvalidTextContent,
    UnsupportedExtraction,
    extractor_for,
)
from suitsflow.services.pdf_text import PdfExtractionUnavailable
from suitsflow.services.saved_extractions import SavedExtractions
from suitsflow.services.storage import ObjectStorage, StorageUnavailable


class ClaimLost(Exception):
    pass


class ExtractionJobs:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> ExtractionJobResponse:
        require_document_access(principal, write=True)
        try:
            version = await DocumentRepository(self.session).version(
                principal.tenant_id, document_id, version_id, lock=True
            )
            if version is None:
                raise ResourceNotFound
            if version.content_status != "clean":
                raise ContentNotCleared
            job = await self.session.scalar(
                select(DocumentExtractionJob)
                .where(
                    DocumentExtractionJob.tenant_id == principal.tenant_id,
                    DocumentExtractionJob.version_id == version_id,
                    DocumentExtractionJob.extractor == extractor_for(version.mime_type),
                )
                .with_for_update()
            )
            if job is None:
                job = DocumentExtractionJob(
                    tenant_id=principal.tenant_id,
                    version_id=version_id,
                    requested_by=principal.user_id,
                    extractor=extractor_for(version.mime_type),
                )
                self.session.add(job)
            elif job.status != "failed":
                result = ExtractionJobResponse.model_validate(job)
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
                action="document.version_extraction_queued",
                version_number=version.version_number,
            )
            result = ExtractionJobResponse.model_validate(job)
            await self.session.commit()
            return result
        except BaseException:
            await self.session.rollback()
            raise

    async def get(
        self, principal: Principal, document_id: UUID, version_id: UUID
    ) -> ExtractionJobResponse:
        require_document_access(principal)
        version = await DocumentRepository(self.session).version(
            principal.tenant_id, document_id, version_id
        )
        if version is None:
            raise ResourceNotFound
        job = await self.session.scalar(
            select(DocumentExtractionJob).where(
                DocumentExtractionJob.tenant_id == principal.tenant_id,
                DocumentExtractionJob.version_id == version_id,
                DocumentExtractionJob.extractor == extractor_for(version.mime_type),
            )
        )
        if job is None:
            raise ResourceNotFound
        return ExtractionJobResponse.model_validate(job)

    async def run_one(self, storage: ObjectStorage) -> bool:
        job = await self.session.scalar(
            select(DocumentExtractionJob)
            .where(
                or_(
                    DocumentExtractionJob.status == "pending",
                    (DocumentExtractionJob.status == "running")
                    & (DocumentExtractionJob.lease_until < datetime.now(UTC)),
                )
            )
            .order_by(DocumentExtractionJob.created_at, DocumentExtractionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            await self.session.rollback()
            return False
        job.status, job.claim_token = "running", uuid4()
        job.lease_until = datetime.now(UTC) + timedelta(minutes=15)
        job.attempts += 1
        job_id, token, tenant_id, version_id, actor, parser = (
            job.id,
            job.claim_token,
            job.tenant_id,
            job.version_id,
            job.requested_by,
            job.extractor,
        )
        await self.session.commit()
        identity = Identity(actor, tenant_id)
        principal = await MembershipRepository(self.session).get_principal(identity)
        version = await self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.tenant_id == tenant_id, DocumentVersion.id == version_id
            )
        )
        assert version is not None
        document_id, number, current_parser = (
            version.document_id,
            version.version_number,
            extractor_for(version.mime_type),
        )
        await self.session.rollback()

        async def locked_claim() -> DocumentExtractionJob:
            claimed = await self.session.scalar(
                select(DocumentExtractionJob)
                .where(DocumentExtractionJob.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                claimed is None
                or claimed.status != "running"
                or claimed.claim_token != token
                or claimed.lease_until is None
                or claimed.lease_until <= datetime.now(UTC)
            ):
                raise ClaimLost
            return claimed

        async def complete(result_id: UUID) -> None:
            # SavedExtractions holds the revision lock: always version, then job.
            claimed = await locked_claim()
            claimed.status, claimed.result_id = "completed", result_id
            claimed.claim_token, claimed.lease_until = None, None
            assert principal is not None
            await AuditRepository(self.session).record_document_event(
                principal,
                document_id,
                action="document.version_extraction_completed",
                version_number=number,
            )
            # The caller commits artifact, completion and audits together.

        try:
            if principal is None:
                raise AccessDenied
            require_document_access(principal, write=True)
            if parser != current_parser:
                raise UnsupportedExtraction
            await SavedExtractions(DocumentRepository(self.session)).save(
                principal, document_id, version_id, storage, on_publish=complete
            )
        except ClaimLost:
            await self.session.rollback()
        except (
            AccessDenied,
            ContentNotCleared,
            ContentNotUploaded,
            ResourceNotFound,
            UnsupportedExtraction,
            ExtractionTooLarge,
            InvalidTextContent,
            StorageUnavailable,
            PdfExtractionUnavailable,
        ):
            await self.session.rollback()
            await DocumentRepository(self.session).version(
                tenant_id, document_id, version_id, lock=True
            )
            try:
                claimed = await locked_claim()
            except ClaimLost:
                await self.session.rollback()
                return True
            claimed.status = "failed"
            claimed.claim_token, claimed.lease_until = None, None
            current = await MembershipRepository(self.session).get_principal(identity)
            if current is not None and "tenant_admin" in current.roles:
                await AuditRepository(self.session).record_document_event(
                    current,
                    document_id,
                    action="document.version_extraction_failed",
                    version_number=number,
                )
            await self.session.commit()
        return True
