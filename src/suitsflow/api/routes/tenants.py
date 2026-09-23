from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.api.dependencies import get_principal
from suitsflow.core.security import AccessDenied, Principal, ResourceNotFound
from suitsflow.db.session import get_session
from suitsflow.repositories.tenants import TenantRepository
from suitsflow.schemas.tenant import TenantNameUpdate, TenantResponse
from suitsflow.services.tenants import TenantService

router = APIRouter()


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    service = TenantService(TenantRepository(session))
    try:
        return await service.get_tenant(principal, tenant_id)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Tenant not found") from exc


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant_name(
    tenant_id: UUID,
    update: TenantNameUpdate,
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    try:
        return await TenantService(TenantRepository(session)).update_name(
            principal, tenant_id, update
        )
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    except ResourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
