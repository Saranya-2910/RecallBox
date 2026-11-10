"""Tests for health check and service status endpoints."""
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from httpx import AsyncClient

from app.db.session import get_db
from app.main import app


@pytest.mark.asyncio
async def test_health_check_success(client: AsyncClient):
    """Confirm GET /health returns 200 and indicates connected database."""
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "environment" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_api_v1_health_check_success(client: AsyncClient):
    """Confirm GET /api/v1/health also functions properly."""
    response = await client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Confirm root metadata endpoint returns service links."""
    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["name"] == "RecallBox"
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


@pytest.mark.asyncio
async def test_health_check_db_failure(client: AsyncClient):
    """Confirm GET /health returns 503 when the database is unreachable."""
    async def broken_db_override():
        mock_session = AsyncMock()
        mock_session.execute.side_effect = ConnectionError("Could not connect to database")
        yield mock_session

    app.dependency_overrides[get_db] = broken_db_override
    try:
        response = await client.get("/health")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

        data = response.json()
        assert data["detail"]["status"] == "unhealthy"
        assert data["detail"]["database"] == "disconnected"
    finally:
        app.dependency_overrides.clear()
