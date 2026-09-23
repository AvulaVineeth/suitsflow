from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from suitsflow.api.router import api_router
from suitsflow.core.config import Settings, get_settings
from suitsflow.db.session import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HTTP application without coupling routes to process globals."""
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = application_settings
        database = Database(application_settings)
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    app = FastAPI(
        title=application_settings.app_name,
        version="0.1.0",
        debug=application_settings.debug,
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix=application_settings.api_v1_prefix)
    return app


app = create_app()
