from uuid import UUID

from suitsflow.core.security import Principal, ResourceNotFound, require_tenant_read
from suitsflow.repositories.audit import AuditRepository
from suitsflow.repositories.tenants import TenantRepository
from suitsflow.schemas.tenant import TenantNameUpdate, TenantResponse


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

    async def update_name(
        self, principal: Principal, tenant_id: UUID, update: TenantNameUpdate
    ) -> TenantResponse:
        # Both tenant administration operations currently require tenant_admin.
        require_tenant_read(principal)
        session = self.repository.session
        try:
            tenant = await self.repository.lock_active(
                tenant_scope=principal.tenant_id, tenant_id=tenant_id
            )
            if tenant is None:
                raise ResourceNotFound
            if tenant.name != update.name:
                old_name = tenant.name
                tenant.name = update.name
                await session.flush()
                await AuditRepository(session).record_tenant_name_change(
                    principal, tenant_id, old_name=old_name, new_name=update.name
                )
                await session.refresh(tenant)
            response = TenantResponse.model_validate(tenant)
            await session.commit()
            return response
        except Exception:
            await session.rollback()
            raise
