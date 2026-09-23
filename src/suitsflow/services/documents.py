from uuid import UUID

from sqlalchemy import func

from suitsflow.core.security import Principal, ResourceNotFound, require_document_access
from suitsflow.db.models import Document, DocumentVersion
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    VersionCreate,
    VersionResponse,
)


class DocumentService:
    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    async def create(self, principal: Principal, request: DocumentCreate) -> DocumentResponse:
        require_document_access(principal, write=True)
        session = self.repository.session
        try:
            document = Document(
                tenant_id=principal.tenant_id, created_by=principal.user_id, **request.model_dump()
            )
            session.add(document)
            await session.flush()
            await AuditRepository(session).record_document_event(
                principal, document.id, action="document.created"
            )
            response = DocumentResponse.model_validate(document)
            await session.commit()
            return response
        except Exception:
            await session.rollback()
            raise

    async def get(self, principal: Principal, document_id: UUID) -> DocumentResponse:
        require_document_access(principal)
        document = await self.repository.get(principal.tenant_id, document_id)
        if document is None:
            raise ResourceNotFound
        return DocumentResponse.model_validate(document)

    async def list_documents(
        self, principal: Principal, *, limit: int, offset: int
    ) -> list[DocumentResponse]:
        require_document_access(principal)
        return [
            DocumentResponse.model_validate(row)
            for row in await self.repository.list(principal.tenant_id, limit=limit, offset=offset)
        ]

    async def add_version(
        self, principal: Principal, document_id: UUID, request: VersionCreate
    ) -> VersionResponse:
        require_document_access(principal, write=True)
        session = self.repository.session
        try:
            document = await self.repository.get(principal.tenant_id, document_id, lock=True)
            if document is None:
                raise ResourceNotFound
            number = await self.repository.next_version_number(principal.tenant_id, document_id)
            version = DocumentVersion(
                tenant_id=principal.tenant_id,
                document_id=document_id,
                version_number=number,
                created_by=principal.user_id,
                **request.model_dump(),
            )
            session.add(version)
            document.updated_at = func.now()
            await session.flush()
            await AuditRepository(session).record_document_event(
                principal, document_id, action="document.version_registered", version_number=number
            )
            response = VersionResponse.model_validate(version)
            await session.commit()
            return response
        except Exception:
            await session.rollback()
            raise

    async def versions(
        self, principal: Principal, document_id: UUID, *, limit: int, offset: int
    ) -> list[VersionResponse]:
        await self.get(principal, document_id)
        return [
            VersionResponse.model_validate(row)
            for row in await self.repository.versions(
                principal.tenant_id, document_id, limit=limit, offset=offset
            )
        ]
