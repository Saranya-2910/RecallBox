"""Question Answering (RAG) service with strict grounding, prompt engineering, and citation validation."""
import logging
import re
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qa_log import QALog
from app.schemas.qa import AskResponse, CitationItem
from app.schemas.search import SearchMode, SearchResultItem
from app.services.embedding import EmbeddingProvider
from app.services.llm import LLMProvider
from app.services.search import search_user_chunks

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are RecallBox, an expert AI assistant that answers questions STRICTLY and ONLY using the provided context chunks from the user's personal library.

Rules:
1. Answer the question using ONLY information explicitly stated in the context passages.
2. If the context does not contain sufficient facts to answer the question truthfully, reply with: "This information is not found in your saved material."
3. Do NOT extrapolate, speculate, or incorporate external world knowledge beyond what is in the passages.
4. For every fact or statement you make, cite the corresponding source chunk using the format [Chunk ID] (e.g., [Chunk 42]).
5. Never invent or hallucinate chunk IDs.
"""


def build_rag_prompt(question: str, chunks: List[SearchResultItem]) -> str:
    """Format context passages and question for LLM grounding."""
    if not chunks:
        return f"No context passages found in user library.\n\nQuestion: {question}\nAnswer:"

    context_lines = []
    for item in chunks:
        page_str = f"Page {item.page_number}" if item.page_number else "N/A"
        context_lines.append(
            f"[Chunk {item.chunk_id}] Document: \"{item.document_title}\" ({page_str})\n{item.snippet}\n"
        )

    context_block = "\n".join(context_lines)
    return f"Context Passages:\n{context_block}\nQuestion: {question}\nAnswer:"


def extract_and_validate_citations(
    answer: str, retrieved_chunks: List[SearchResultItem]
) -> Tuple[List[CitationItem], List[int]]:
    """Extract cited chunk IDs from answer and validate against retrieved set.

    Drops any hallucinated IDs that were not present in the retrieved context.
    """
    retrieved_map = {item.chunk_id: item for item in retrieved_chunks}

    # Match both [Chunk 123] and [123] citation patterns
    raw_citations = re.findall(r"\[(?:Chunk\s+)?(\d+)\]", answer, re.IGNORECASE)

    valid_citations: List[CitationItem] = []
    valid_chunk_ids: List[int] = []
    seen_ids = set()

    for cid_str in raw_citations:
        try:
            cid = int(cid_str)
        except ValueError:
            continue

        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        if cid in retrieved_map:
            match = retrieved_map[cid]
            valid_chunk_ids.append(cid)
            valid_citations.append(
                CitationItem(
                    chunk_id=match.chunk_id,
                    document_id=match.document_id,
                    document_title=match.document_title,
                    page_number=match.page_number,
                    snippet=match.snippet,
                )
            )
        else:
            logger.warning(
                "Dropped hallucinated chunk citation ID %d not in retrieved context %s",
                cid,
                list(retrieved_map.keys()),
            )

    return valid_citations, valid_chunk_ids


async def answer_rag_question(
    question: str,
    user_id: int,
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    llm_provider: LLMProvider,
    document_ids: Optional[List[int]] = None,
    top_k: int = 5,
) -> AskResponse:
    """Retrieve top passages with hybrid search, query LLM, validate citations, and audit log."""
    clean_question = question.strip()

    # Step 1: Hybrid retrieval scoped to user
    retrieved_chunks = await search_user_chunks(
        query=clean_question,
        user_id=user_id,
        db=db,
        embedding_provider=embedding_provider,
        mode=SearchMode.HYBRID,
        k=60,
        limit=top_k,
        document_ids=document_ids,
    )

    # Step 2: Assemble prompt
    prompt = build_rag_prompt(clean_question, retrieved_chunks)

    # Step 3: Generate grounded completion
    raw_answer = await llm_provider.generate_response(
        prompt=prompt, system_instruction=SYSTEM_PROMPT
    )

    # Step 4: Validate citations and filter hallucinations
    citations, cited_chunk_ids = extract_and_validate_citations(
        raw_answer, retrieved_chunks
    )

    # Step 5: Audit log in qa_logs
    qa_log = QALog(
        user_id=user_id,
        question=clean_question,
        answer=raw_answer,
        cited_chunk_ids=cited_chunk_ids,
    )
    db.add(qa_log)
    await db.commit()
    await db.refresh(qa_log)

    return AskResponse(
        question=clean_question,
        answer=raw_answer,
        citations=citations,
        qa_log_id=qa_log.id,
    )
