"""Tests verifying strict user data isolation and tenancy scoping."""
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest.mark.asyncio
async def test_user_isolation_me_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Verify user A cannot read user B's account data via authenticated endpoints."""
    # Create User A
    user_a = User(
        email="user_a@example.com",
        password_hash=get_password_hash("PasswordA123!"),
    )
    # Create User B
    user_b = User(
        email="user_b@example.com",
        password_hash=get_password_hash("PasswordB123!"),
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    assert user_a.id != user_b.id

    token_a = create_access_token(data={"sub": str(user_a.id), "email": user_a.email})
    token_b = create_access_token(data={"sub": str(user_b.id), "email": user_b.email})

    # User A accesses /auth/me
    response_a = await client.get("/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert response_a.status_code == status.HTTP_200_OK
    data_a = response_a.json()
    assert data_a["id"] == user_a.id
    assert data_a["email"] == "user_a@example.com"
    assert data_a["id"] != user_b.id

    # User B accesses /auth/me
    response_b = await client.get("/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert response_b.status_code == status.HTTP_200_OK
    data_b = response_b.json()
    assert data_b["id"] == user_b.id
    assert data_b["email"] == "user_b@example.com"
    assert data_b["id"] != user_a.id


@pytest.mark.asyncio
async def test_user_cannot_access_with_nonexistent_subject(client: AsyncClient):
    """Verify a forged token with non-existent user_id is rejected."""
    fake_token = create_access_token(data={"sub": "999999", "email": "fake@example.com"})
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "User not found"
