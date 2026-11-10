"""Pydantic schemas for semantic, keyword, and hybrid search requests and responses."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    """Available search retrieval modes."""
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class SearchResultItem(BaseModel):
    """A retrieved chunk passage with source document metadata and relevance score."""
    chunk_id: int = Field(..., description="Chunk ID")
    document_id: int = Field(..., description="Parent document ID")
    document_title: str = Field(..., description="Parent document title")
    source_type: str = Field(..., description="Document source type (pdf, link, note)")
    page_number: Optional[int] = Field(None, description="Page number if available")
    snippet: str = Field(..., description="Extracted passage text")
    score: float = Field(..., description="Relevance score (cosine similarity, ts_rank, or RRF)")
    chunk_index: int = Field(..., description="Zero-based index of chunk within document")


class SearchResponse(BaseModel):
    """Collection of ranked search results."""
    query: str = Field(..., description="Original search query")
    mode: str = Field(..., description="Search mode utilized (semantic, keyword, hybrid)")
    total_results: int = Field(..., description="Total retrieved matches")
    results: List[SearchResultItem] = Field(..., description="Ranked and de-duplicated chunk results")
