"""API endpoints package."""
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.search import router as search_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(documents_router)
api_router.include_router(search_router)

__all__ = ["api_router", "auth_router", "documents_router", "health_router", "search_router"]
