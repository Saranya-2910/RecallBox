"""Pydantic schemas for system health and status endpoints."""
from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """Schema for /health response."""
    status: str = Field(..., description="Overall service status (e.g., 'ok', 'unhealthy')")
    database: str = Field(..., description="Database connectivity status (e.g., 'connected', 'disconnected')")
    environment: str = Field(..., description="Application execution environment")
    version: str = Field(..., description="Application version")
