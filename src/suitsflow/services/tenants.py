from uuid import UUID

from suitsflow.core.security import Principal, ResourceNotFound, require_tenant_read
from suitsflow.repositories.tenants import TenantRepository
from suitsflow.schemas.tenant import TenantResponse


class TenantService:
    def __init__(self, repository: TenantRepository) -> None:
        self.repository = repository

    async def get_tenant(self, principal: Principal, tenant_id: UUID) -> TenantResponse:
        require_tenant_read(principal)
        tenant = await self.repository.get_active(
            tenant_scope=principal.tenant_id, tenant_id=tenant_id
        )
        if tenant is None:
            raise ResourceNotFound
        return TenantResponse.model_validate(tenant)
