"""Tests for authentication endpoints: registration, login, JWT validation, and rate limiting."""
from datetime import timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, login_rate_limiter, verify_password
from app.models.user import User


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession):
    """Test successful user registration returns 201 and omits password."""
    payload = {"email": "newuser@example.com", "password": "StrongPassword123!"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_passwords_never_stored_in_plain_text(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify passwords are never stored in plain text in the database."""
    raw_password = "MySuperSecretPassword123!"
    payload = {"email": "plaincheck@example.com", "password": raw_password}

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED

    user_id = response.json()["id"]
    user = await db_session.scalar(select(User).where(User.id == user_id))
    assert user is not None
    assert user.password_hash != raw_password
    assert user.password_hash.startswith("$2")
    assert verify_password(raw_password, user.password_hash) is True


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    """Test registering an existing email returns 400 Bad Request."""
    payload = {"email": test_user.email, "password": "AnotherPassword123!"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Email is already registered"


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """Test registration with invalid email format returns 422."""
    payload = {"email": "not-an-email", "password": "StrongPassword123!"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """Test registration with password under 8 characters returns 422."""
    payload = {"email": "shortpass@example.com", "password": "short"}
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    """Test login with valid credentials returns JWT access token."""
    payload = {"email": test_user.email, "password": "securePassword123!"}
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, test_user: User):
    """Test login with invalid password returns 401."""
    payload = {"email": test_user.email, "password": "WrongPassword123!"}
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with unregistered email returns 401."""
    payload = {"email": "ghost@example.com", "password": "Password123!"}
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_rate_limiting(client: AsyncClient, test_user: User):
    """Test login rate limiting triggers 429 after exceeding max attempts."""
    login_rate_limiter.reset()
    payload = {"email": test_user.email, "password": "WrongPassword123!"}

    # Attempt 5 times (allowed to fail)
    for _ in range(5):
        res = await client.post("/auth/login", json=payload)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # 6th attempt must be rate-limited
    res_limited = await client.post("/auth/login", json=payload)
    assert res_limited.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Too many login attempts" in res_limited.json()["detail"]

    # Reset limiter for subsequent tests
    login_rate_limiter.reset()


@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient, test_user: User, test_user_auth_headers: dict):
    """Test GET /auth/me returns the authenticated user."""
    response = await client.get("/auth/me", headers=test_user_auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email


@pytest.mark.asyncio
async def test_get_me_unauthorized_missing_token(client: AsyncClient):
    """Test protected route returns 401 without authorization header."""
    response = await client.get("/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_me_malformed_token(client: AsyncClient):
    """Test protected route returns 401 when token is malformed."""
    headers = {"Authorization": "Bearer not-a-valid-jwt-token"}
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_get_me_expired_token(client: AsyncClient, test_user: User):
    """Test protected route returns 401 when token has expired."""
    expired_token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email},
        expires_delta=timedelta(seconds=-10),  # expired in the past
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Token has expired"
