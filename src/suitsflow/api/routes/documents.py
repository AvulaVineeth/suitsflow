from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.api.dependencies import get_principal
from suitsflow.core.security import (
    AccessDenied,
    Principal,
    ResourceNotFound,
    require_document_access,
)
from suitsflow.db.session import get_session
from suitsflow.repositories.documents import DocumentRepository
from suitsflow.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    VersionCreate,
    VersionResponse,
)
from suitsflow.services.documents import DocumentService
from suitsflow.services.storage import ObjectStorage, S3Storage, StorageUnavailable
from suitsflow.services.upload_validation import InvalidUpload
from suitsflow.services.uploads import UploadService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_reader(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    try:
        require_document_access(principal)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    return principal


def get_writer(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    try:
        require_document_access(principal, write=True)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    return principal


def get_service(session: Annotated[AsyncSession, Depends(get_session)]) -> DocumentService:
    return DocumentService(DocumentRepository(session))


Reader = Annotated[Principal, Depends(get_reader)]
Writer = Annotated[Principal, Depends(get_writer)]
Service = Annotated[DocumentService, Depends(get_service)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]


def get_storage(request: Request) -> ObjectStorage:
    settings = request.app.state.settings
    if settings.s3_bucket is None:
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    return S3Storage(settings.s3_bucket, settings.s3_region)


@router.put("/{document_id}/versions/{version_id}/content", response_model=VersionResponse)
async def upload_content(
    document_id: UUID,
    version_id: UUID,
    request: Request,
    principal: Writer,
    service: Service,
    storage: Annotated[ObjectStorage, Depends(get_storage)],
) -> VersionResponse:
    try:
        return await UploadService(service.repository, storage).upload(
            principal,
            document_id,
            version_id,
            request.stream(),
            request.headers.get("content-type", ""),
            request.app.state.settings.upload_timeout_seconds,
        )
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Document version not found") from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except InvalidUpload as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Upload timed out") from exc
    except StorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Document storage unavailable") from exc


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(
    request: DocumentCreate, principal: Writer, service: Service
) -> DocumentResponse:
    return await service.create(principal, request)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    principal: Reader, service: Service, limit: Limit = 50, offset: Offset = 0
) -> list[DocumentResponse]:
    return await service.list_documents(principal, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, principal: Reader, service: Service) -> DocumentResponse:
    try:
        return await service.get(principal, document_id)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@router.post("/{document_id}/versions", response_model=VersionResponse, status_code=201)
async def add_version(
    document_id: UUID, request: VersionCreate, principal: Writer, service: Service
) -> VersionResponse:
    try:
        return await service.add_version(principal, document_id, request)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@router.get("/{document_id}/versions", response_model=list[VersionResponse])
async def list_versions(
    document_id: UUID, principal: Reader, service: Service, limit: Limit = 50, offset: Offset = 0
) -> list[VersionResponse]:
    try:
        return await service.versions(principal, document_id, limit=limit, offset=offset)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
