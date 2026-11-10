"""Pydantic schemas for document ingestion, filtering, and responses."""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    """Permitted source types for intake."""
    PDF = "pdf"
    LINK = "link"
    NOTE = "note"


class DocumentStatus(str, Enum):
    """Document processing pipeline states."""
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class CreateLinkRequest(BaseModel):
    """Payload to save an external URL link."""
    url: AnyHttpUrl = Field(..., description="Valid HTTP/HTTPS URL")
    title: Optional[str] = Field(None, max_length=255, description="Optional custom document title")
    category: Optional[str] = Field(None, max_length=100, description="Optional classification category")


class CreateNoteRequest(BaseModel):
    """Payload to store a plain markdown or text note."""
    title: str = Field(..., min_length=1, max_length=255, description="Note title")
    content: str = Field(..., min_length=1, description="Raw note text or markdown content")
    category: Optional[str] = Field(None, max_length=100, description="Optional classification category")


class DocumentResponse(BaseModel):
    """Serialized document detail response."""
    id: int = Field(..., description="Document identifier")
    user_id: int = Field(..., description="Owner user ID")
    title: str = Field(..., description="Document title")
    source_type: str = Field(..., description="Intake source type (pdf, link, note)")
    source_url: Optional[str] = Field(None, description="Original source link if applicable")
    file_path: Optional[str] = Field(None, description="Local or object storage path")
    status: str = Field(..., description="Processing status (pending, processing, ready, failed)")
    error: Optional[str] = Field(None, description="Processing error message if failed")
    category: Optional[str] = Field(None, description="Document category")
    summary: Optional[str] = Field(None, description="AI-generated document summary")
    created_at: datetime = Field(..., description="Intake timestamp")

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated collection of documents."""
    items: List[DocumentResponse] = Field(..., description="Page of documents")
    total: int = Field(..., description="Total documents matching filters")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Page size limit")
    pages: int = Field(..., description="Total available pages")
