from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.db.models import Tenant


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self, *, tenant_scope: UUID, tenant_id: UUID) -> Tenant | None:
        result = await self.session.scalars(
            select(Tenant).where(
                Tenant.id == tenant_scope, Tenant.id == tenant_id, Tenant.status == "active"
            )
        )
        return result.one_or_none()

    async def lock_active(self, *, tenant_scope: UUID, tenant_id: UUID) -> Tenant | None:
        result = await self.session.scalars(
            select(Tenant)
            .where(Tenant.id == tenant_scope, Tenant.id == tenant_id, Tenant.status == "active")
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.one_or_none()
