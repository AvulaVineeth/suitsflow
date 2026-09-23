import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from suitsflow.core.config import Settings
from suitsflow.core.security import Principal

bearer = HTTPBearer(auto_error=False)


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
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
    return Principal(
        user_id=settings.development_user_id,
        tenant_id=settings.development_tenant_id,
        roles=frozenset({settings.development_role}),
    )
