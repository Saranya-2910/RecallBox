"""Q&A endpoint: Cited Question Answering (RAG) using user knowledge base."""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.qa import AskRequest, AskResponse
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.llm import LLMProvider, get_llm_provider
from app.services.qa import answer_rag_question

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Question Answering"])


@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question and receive a grounded answer with citations",
)
async def ask_question(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedding: EmbeddingProvider = Depends(get_embedding_provider),
    llm: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    """Retrieve top passages with hybrid search, synthesize answer, and validate citations."""
    return await answer_rag_question(
        question=payload.question,
        user_id=current_user.id,
        db=db,
        embedding_provider=embedding,
        llm_provider=llm,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
