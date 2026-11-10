"""Pydantic schemas for document tags."""
from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    """Base tag properties."""
    name: str = Field(..., min_length=1, max_length=100, description="Tag name")


class TagCreate(TagBase):
    """Payload to add a tag."""
    pass


class TagResponse(TagBase):
    """Public tag schema."""
    id: int = Field(..., description="Tag ID")

    model_config = ConfigDict(from_attributes=True)
