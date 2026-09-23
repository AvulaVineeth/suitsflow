from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from suitsflow.core.config import Settings


class Database:
    """One connection pool per application lifespan; no connections at import time."""

    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_timeout=settings.database_timeout_seconds,
            connect_args={"timeout": settings.database_timeout_seconds},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped session; services own explicit commit boundaries.

    Closing rolls back any uncommitted transaction, including on request failure.
    Never share a session between concurrently running tasks.
    """
    database: Database = request.app.state.database
    async with database.sessions() as session:
        yield session
