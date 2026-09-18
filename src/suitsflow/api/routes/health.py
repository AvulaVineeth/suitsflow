from fastapi import APIRouter, Request, status

from suitsflow.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health(request: Request) -> HealthResponse:
    """Return process liveness without checking external dependencies."""
    settings = request.app.state.settings
    return HealthResponse(status="ok", environment=settings.environment)


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def ready(request: Request) -> HealthResponse:
    """Return readiness for dependencies configured in the current release."""
    settings = request.app.state.settings
    return HealthResponse(status="ok", environment=settings.environment)
