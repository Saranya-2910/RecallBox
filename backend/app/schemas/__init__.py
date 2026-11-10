"""Pydantic schemas package."""
from app.schemas.auth import LoginRequest, TokenPayload, TokenResponse
from app.schemas.document import (
    CreateLinkRequest,
    CreateNoteRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    SourceType,
)
from app.schemas.health import HealthCheckResponse
from app.schemas.qa import AskRequest, AskResponse, CitationItem
from app.schemas.related import RelatedDocumentItem, RelatedDocumentsResponse
from app.schemas.search import SearchMode, SearchResponse, SearchResultItem
from app.schemas.tag import TagBase, TagCreate, TagResponse
from app.schemas.user import UserBase, UserRegister, UserResponse

__all__ = [
    "HealthCheckResponse",
    "UserBase",
    "UserRegister",
    "UserResponse",
    "LoginRequest",
    "TokenResponse",
    "TokenPayload",
    "SourceType",
    "DocumentStatus",
    "CreateLinkRequest",
    "CreateNoteRequest",
    "DocumentResponse",
    "DocumentListResponse",
    "SearchMode",
    "SearchResultItem",
    "SearchResponse",
    "AskRequest",
    "AskResponse",
    "CitationItem",
    "TagBase",
    "TagCreate",
    "TagResponse",
    "RelatedDocumentItem",
    "RelatedDocumentsResponse",
]
