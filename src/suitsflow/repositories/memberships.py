from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.core.security import Identity, Principal
from suitsflow.db.models import Role, Tenant, User, UserRole


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_principal(self, identity: Identity) -> Principal | None:
        """Read active membership and current roles in one tenant-scoped statement."""
        result = await self.session.execute(
            select(User.id, Role.name)
            .select_from(User)
            .join(Tenant, Tenant.id == User.tenant_id)
            .outerjoin(
                UserRole, and_(UserRole.tenant_id == User.tenant_id, UserRole.user_id == User.id)
            )
            .outerjoin(
                Role, and_(Role.tenant_id == UserRole.tenant_id, Role.id == UserRole.role_id)
            )
            .where(
                User.id == identity.user_id,
                User.tenant_id == identity.tenant_id,
                User.status == "active",
                Tenant.status == "active",
            )
        )
        rows = result.all()
        if not rows:
            return None
        return Principal(
            user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            roles=frozenset(name for _, name in rows if name is not None),
        )
