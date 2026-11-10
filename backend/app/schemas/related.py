"""Pydantic schemas for related documents endpoints."""
from typing import List, Optional

from pydantic import BaseModel, Field


class RelatedDocumentItem(BaseModel):
    """A semantically similar related document."""
    document_id: int = Field(..., description="Related document ID")
    title: str = Field(..., description="Document title")
    source_type: str = Field(..., description="Document source type (pdf, link, note)")
    summary: Optional[str] = Field(None, description="Document summary")
    category: Optional[str] = Field(None, description="Document category")
    similarity: float = Field(..., description="Embedding cosine similarity score (0.0 to 1.0)")


class RelatedDocumentsResponse(BaseModel):
    """Collection of related documents."""
    document_id: int = Field(..., description="Reference document ID")
    related: List[RelatedDocumentItem] = Field(..., description="Semantically nearest documents")
