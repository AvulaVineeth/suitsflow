from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.core.security import Principal
from suitsflow.db.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_tenant_name_change(
        self, principal: Principal, tenant_id: UUID, *, old_name: str, new_name: str
    ) -> None:
        self.session.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action="tenant.name_updated",
                resource_type="tenant",
                resource_id=tenant_id,
                details={"name": {"before": old_name, "after": new_name}},
            )
        )
        await self.session.flush()

    async def record_document_event(
        self,
        principal: Principal,
        document_id: UUID,
        *,
        action: str,
        version_number: int | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action=action,
                resource_type="document",
                resource_id=document_id,
                details={"version_number": version_number} if version_number is not None else {},
            )
        )
        await self.session.flush()
