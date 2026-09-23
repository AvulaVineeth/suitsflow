from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Identity:
    user_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    roles: frozenset[str]


class AccessDenied(Exception):
    """The authenticated principal lacks permission for this operation."""


class ResourceNotFound(Exception):
    """The resource is absent or not visible to the principal."""


def require_tenant_read(principal: Principal) -> None:
    if "tenant_admin" not in principal.roles:
        raise AccessDenied
