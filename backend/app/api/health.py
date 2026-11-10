"""Health check endpoint confirming service liveness and database connectivity."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.health import HealthCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse, status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthCheckResponse:
    """Perform liveness and database connectivity health check."""
    try:
        result = await db.execute(text("SELECT 1"))
        scalar_val = result.scalar()
        if scalar_val != 1:
            raise ValueError(f"Unexpected database query result: {scalar_val}")
    except Exception as exc:
        logger.error("Health check failed database connectivity test: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(exc),
            },
        ) from exc

    return HealthCheckResponse(
        status="ok",
        database="connected",
        environment=settings.APP_ENV,
        version="0.1.0",
    )
