from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.db.models import Document, DocumentVersion


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def version(
        self, tenant_id: UUID, document_id: UUID, version_id: UUID, *, lock: bool = False
    ) -> DocumentVersion | None:
        query = select(DocumentVersion).where(
            DocumentVersion.tenant_id == tenant_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.id == version_id,
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(query)).one_or_none()

    async def get(
        self, tenant_id: UUID, document_id: UUID, *, lock: bool = False
    ) -> Document | None:
        query = select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(query)).one_or_none()

    async def list(self, tenant_id: UUID, *, limit: int, offset: int) -> Sequence[Document]:
        return (
            await self.session.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id)
                .order_by(Document.created_at.desc(), Document.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()

    async def versions(
        self, tenant_id: UUID, document_id: UUID, *, limit: int, offset: int
    ) -> Sequence[DocumentVersion]:
        return (
            await self.session.scalars(
                select(DocumentVersion)
                .where(
                    DocumentVersion.tenant_id == tenant_id,
                    DocumentVersion.document_id == document_id,
                )
                .order_by(DocumentVersion.version_number)
                .limit(limit)
                .offset(offset)
            )
        ).all()

    async def next_version_number(self, tenant_id: UUID, document_id: UUID) -> int:
        """Caller must hold the document row lock until commit."""
        latest = await self.session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document_id
            )
        )
        return int(latest or 0) + 1
