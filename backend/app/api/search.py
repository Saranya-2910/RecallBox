"""Search endpoints: semantic vector search, full-text search, and hybrid RRF search."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import SearchMode, SearchResponse
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.search import search_user_chunks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Search"])


@router.get(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search user library using semantic, keyword, or hybrid modes",
)
async def search_library(
    q: str = Query(..., min_length=1, description="Search query string"),
    mode: SearchMode = Query(SearchMode.HYBRID, description="Search mode: semantic, keyword, or hybrid"),
    k: int = Query(60, ge=1, le=200, description="Reciprocal Rank Fusion smoothing constant"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of chunks to return"),
    document_ids: Optional[List[int]] = Query(None, description="Optional filter by document IDs"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedding: EmbeddingProvider = Depends(get_embedding_provider),
) -> SearchResponse:
    """Execute ranked retrieval across user's chunks with tenant isolation."""
    results = await search_user_chunks(
        query=q,
        user_id=current_user.id,
        db=db,
        embedding_provider=embedding,
        mode=mode,
        k=k,
        limit=limit,
        document_ids=document_ids,
    )

    return SearchResponse(
        query=q,
        mode=mode.value,
        total_results=len(results),
        results=results,
    )
