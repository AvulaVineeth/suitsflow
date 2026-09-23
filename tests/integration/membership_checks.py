from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from suitsflow.core.config import Settings
from suitsflow.core.security import Identity
from suitsflow.db.models import Role, Tenant, User, UserRole
from suitsflow.db.session import Database
from suitsflow.repositories.memberships import MembershipRepository


async def exercise_memberships(settings: Settings, tenant_id: UUID, other_id: UUID) -> UUID:
    db = Database(settings)
    user_id, other_user_id, admin_role_id, other_role_id = (uuid4() for _ in range(4))
    try:
        async with db.sessions() as session:
            # Email uniqueness is per tenant, so these same-email users are both valid.
            session.add_all(
                [
                    User(id=user_id, tenant_id=tenant_id, email="admin@example.com", name="Admin"),
                    User(
                        id=other_user_id,
                        tenant_id=other_id,
                        email="admin@example.com",
                        name="Other",
                    ),
                    Role(id=admin_role_id, tenant_id=tenant_id, name="tenant_admin"),
                    Role(id=other_role_id, tenant_id=other_id, name="tenant_admin"),
                ]
            )
            await session.flush()
            session.add(UserRole(tenant_id=tenant_id, user_id=user_id, role_id=admin_role_id))
            await session.commit()
        invalid_records = [
            User(tenant_id=tenant_id, email="admin@example.com", name="Duplicate"),
            User(tenant_id=tenant_id, email=" Admin@example.com ", name="Not normalized"),
            User(tenant_id=uuid4(), email="orphan@example.com", name="Orphan"),
            Role(tenant_id=tenant_id, name="tenant_admin"),
            Role(tenant_id=tenant_id, name="superuser"),
            UserRole(tenant_id=tenant_id, user_id=user_id, role_id=other_role_id),
            UserRole(tenant_id=tenant_id, user_id=other_user_id, role_id=admin_role_id),
            UserRole(tenant_id=tenant_id, user_id=user_id, role_id=admin_role_id),
        ]
        for record in invalid_records:
            async with db.sessions() as session:
                session.add(record)
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()
        async with db.sessions() as session:
            with pytest.raises(IntegrityError):
                await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.rollback()
            repository = MembershipRepository(session)
            identity = Identity(user_id=user_id, tenant_id=tenant_id)
            principal = await repository.get_principal(identity)
            assert principal is not None and principal.roles == frozenset({"tenant_admin"})
            assert await repository.get_principal(Identity(user_id, other_id)) is None
            assert await repository.get_principal(Identity(uuid4(), tenant_id)) is None
            no_roles = await repository.get_principal(Identity(other_user_id, other_id))
            assert no_roles is not None and no_roles.roles == frozenset()
            await session.execute(update(User).where(User.id == user_id).values(status="disabled"))
            assert await repository.get_principal(identity) is None
            await session.rollback()
            await session.execute(
                update(Tenant).where(Tenant.id == tenant_id).values(status="suspended")
            )
            assert await repository.get_principal(identity) is None
            await session.rollback()
    finally:
        await db.dispose()
    return user_id


async def revoke_roles(settings: Settings, user_id: UUID) -> None:
    db = Database(settings)
    try:
        async with db.sessions() as session:
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
            await session.commit()
    finally:
        await db.dispose()


async def set_access_status(
    settings: Settings, user_id: UUID, tenant_id: UUID, *, active: bool
) -> None:
    db = Database(settings)
    try:
        async with db.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(status="active" if active else "disabled")
            )
            await session.execute(
                update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(status="active" if active else "suspended")
            )
            await session.commit()
    finally:
        await db.dispose()
