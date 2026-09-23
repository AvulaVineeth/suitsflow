import asyncio
from typing import Annotated

from asyncpg import PostgresError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from suitsflow.db.session import get_session
from suitsflow.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health(request: Request) -> HealthResponse:
    """Return process liveness without checking external dependencies."""
    settings = request.app.state.settings
    return HealthResponse(status="ok", environment=settings.environment)


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def ready(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> HealthResponse:
    """Check database connectivity within a bounded time without exposing credentials."""
    settings = request.app.state.settings
    try:
        async with asyncio.timeout(settings.database_timeout_seconds):
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ok", environment=settings.environment)
