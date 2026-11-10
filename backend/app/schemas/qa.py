"""Pydantic schemas for Question Answering (RAG) and citation responses."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Payload to query user knowledge base with natural language."""
    question: str = Field(..., min_length=1, max_length=1000, description="Natural language question")
    document_ids: Optional[List[int]] = Field(None, description="Optional document ID restrictions")
    top_k: int = Field(5, ge=1, le=20, description="Number of context passages to retrieve")


class CitationItem(BaseModel):
    """Grounded reference citation verified against retrieved document chunks."""
    chunk_id: int = Field(..., description="ID of cited chunk")
    document_id: int = Field(..., description="Parent document ID")
    document_title: str = Field(..., description="Parent document title")
    page_number: Optional[int] = Field(None, description="Document page number if available")
    snippet: str = Field(..., description="Referenced source passage excerpt")


class AskResponse(BaseModel):
    """Synthesized answer accompanied by verified citations and audit logging."""
    question: str = Field(..., description="Question asked")
    answer: str = Field(..., description="Grounded answer text")
    citations: List[CitationItem] = Field(..., description="Verified citations supporting the answer")
    qa_log_id: Optional[int] = Field(None, description="Identifier of the persisted Q&A log entry")
