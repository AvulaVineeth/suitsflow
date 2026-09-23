import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.core.config import Settings
from suitsflow.core.security import Identity, Principal
from suitsflow.db.session import get_session
from suitsflow.repositories.memberships import MembershipRepository

bearer = HTTPBearer(auto_error=False)


def get_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Identity:
    """Resolve only server-configured local identity; production identity comes later."""
    settings: Settings = request.app.state.settings
    if (
        not settings.development_auth_enabled
        or settings.environment not in {"local", "test"}
        or settings.development_auth_token is None
        or settings.development_user_id is None
        or settings.development_tenant_id is None
        or credentials is None
        or not secrets.compare_digest(
            credentials.credentials.encode(),
            settings.development_auth_token.get_secret_value().encode(),
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Identity(
        user_id=settings.development_user_id,
        tenant_id=settings.development_tenant_id,
    )


async def get_principal(
    identity: Annotated[Identity, Depends(get_identity)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    principal = await MembershipRepository(session).get_principal(identity)
    if principal is None:
        raise HTTPException(status_code=403, detail="Access denied")
    return principal
