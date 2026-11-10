"""Pydantic schemas for user registration, serialization, and profile views."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base user properties."""
    email: EmailStr = Field(..., description="Unique email address of the user")


class UserRegister(UserBase):
    """Payload for user registration."""
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext password (minimum 8 characters)",
    )


class UserResponse(UserBase):
    """Public user response schema (password hashes are never exposed)."""
    id: int = Field(..., description="Unique user identifier")
    created_at: datetime = Field(..., description="User creation timestamp")

    model_config = ConfigDict(from_attributes=True)
