"""Pydantic schemas for authentication requests and tokens."""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Payload for user login."""
    email: EmailStr = Field(..., description="Registered user email")
    password: str = Field(..., min_length=1, description="Account password")


class TokenResponse(BaseModel):
    """OAuth2 compatible token response."""
    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenPayload(BaseModel):
    """Decoded JWT payload structure."""
    sub: str = Field(..., description="Subject identifier (user_id)")
    exp: int = Field(..., description="Expiration timestamp (unix epoch)")
    iat: Optional[int] = Field(None, description="Issued-at timestamp")
