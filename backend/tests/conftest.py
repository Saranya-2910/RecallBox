"""Pytest configuration and test fixtures."""
import os
import shutil
from pathlib import Path
from typing import AsyncGenerator, Dict

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, login_rate_limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.storage import LocalStorageService, get_storage_service

# Configure test environment and storage directory
settings.APP_ENV = "testing"
TEST_STORAGE_PATH = Path("./test_storage").resolve()
settings.LOCAL_STORAGE_DIR = str(TEST_STORAGE_PATH)

# Determine test database URL: use TEST_DATABASE_URL if provided, else SQLite in-memory with StaticPool
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in TEST_DB_URL else {},
    poolclass=StaticPool if "sqlite" in TEST_DB_URL else None,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup test database tables and storage before each test and drop after."""
    login_rate_limiter.reset()
    TEST_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    if TEST_STORAGE_PATH.exists():
        shutil.rmtree(TEST_STORAGE_PATH, ignore_errors=True)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a scoped transactional database session for tests."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_storage() -> LocalStorageService:
    """Fixture providing local storage service targeting test storage directory."""
    return LocalStorageService(base_dir=str(TEST_STORAGE_PATH))


@pytest.fixture
async def client(
    db_session: AsyncSession, test_storage: LocalStorageService
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP async client with dependency overrides for test database and storage."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def override_get_storage() -> LocalStorageService:
        return test_storage

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = override_get_storage

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Fixture providing a persisted test user."""
    user = User(
        email="testuser@example.com",
        password_hash=get_password_hash("securePassword123!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_user_auth_headers(test_user: User) -> Dict[str, str]:
    """Provide authorization headers containing a valid JWT for test_user."""
    token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}
