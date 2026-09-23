from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
