from fastapi import APIRouter

from suitsflow.api.routes.documents import router as documents_router
from suitsflow.api.routes.health import router as health_router
from suitsflow.api.routes.tenants import router as tenants_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(tenants_router, tags=["tenants"])
api_router.include_router(documents_router)
