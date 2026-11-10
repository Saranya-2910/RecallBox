"""Authentication endpoints: register, login (JWT), and current user profile."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    get_password_hash,
    login_rate_limiter,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRegister, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register_user(
    payload: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user with email and secure password."""
    normalized_email = payload.email.lower().strip()

    # Check for existing email to prevent duplicates
    stmt = select(User).where(User.email == normalized_email)
    existing_user = await db.scalar(stmt)
    if existing_user:
        logger.warning("Registration rejected: email %s already in use", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    # Password is never stored or logged in plaintext
    password_hash = get_password_hash(payload.password)
    user = User(email=normalized_email, password_hash=password_hash)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered successfully with id=%d", user.id)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT access token",
)
async def login_user(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password, returning a signed JWT."""
    normalized_email = payload.email.lower().strip()
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{normalized_email}"

    # Rate limiting on login attempts
    if not login_rate_limiter.is_allowed(rate_limit_key):
        logger.warning(
            "Rate limit exceeded for login attempts from key: %s",
            rate_limit_key,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    # Fetch user by email
    stmt = select(User).where(User.email == normalized_email)
    user = await db.scalar(stmt)

    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("Failed login attempt for email: %s", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reset rate limit tracker on successful authentication
    login_rate_limiter.reset(rate_limit_key)

    # Generate JWT token with user_id as subject
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})

    logger.info("User id=%d logged in successfully", user.id)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return profile information for the authenticated user."""
    return current_user
