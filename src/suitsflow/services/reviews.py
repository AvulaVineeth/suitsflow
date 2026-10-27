"""Authorized bridge between immutable extractions and the review graph."""

from uuid import UUID

from suitsflow.agents.review import ReviewModel, ReviewResult, run_review
from suitsflow.core.security import (
    AccessDenied,
    Identity,
    Principal,
    ResourceNotFound,
    require_document_access,
)
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.repositories.memberships import MembershipRepository
from suitsflow.schemas.extraction import SavedExtractionResponse
from suitsflow.services.downloads import ContentNotCleared
from suitsflow.services.saved_extractions import SavedExtractions
from suitsflow.services.storage import ObjectStorage


class UnsupportedReviewSource(Exception):
    pass


class ReviewService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStorage) -> None:
        self.repository = repository
        self.storage = storage

    async def review(
        self, principal: Principal, document_id: UUID, version_id: UUID, model: ReviewModel
    ) -> ReviewResult:
        session = self.repository.session

        async def authorize() -> Principal:
            try:
                current = await MembershipRepository(session).get_principal(
                    Identity(principal.user_id, principal.tenant_id)
                )
                if current is None:
                    raise AccessDenied
                require_document_access(current)
                return current
            finally:
                await session.rollback()

        async def load() -> SavedExtractionResponse:
            current = await authorize()
            document = await self.repository.get(principal.tenant_id, document_id)
            if document is None:
                raise ResourceNotFound
            if document.document_type != "contract":
                raise UnsupportedReviewSource
            return await SavedExtractions(self.repository).get(
                current, document_id, version_id, self.storage
            )

        async def reauthorize() -> None:
            await authorize()
            try:
                version = await self.repository.version(
                    principal.tenant_id, document_id, version_id
                )
                if version is None or version.content_status != "clean":
                    raise ContentNotCleared
            finally:
                await session.rollback()

        try:
            return await run_review(load_source=load, reauthorize=reauthorize, model=model)
        finally:
            await session.rollback()
