"""Search service: semantic vector search, full-text keyword search, and Reciprocal Rank Fusion."""
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.search import SearchMode, SearchResultItem
from app.services.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class ScoredChunk:
    """Internal container for retrieved chunk with associated document metadata and score."""
    chunk: Chunk
    document: Document
    score: float


def compute_reciprocal_rank_fusion(
    semantic_results: List[ScoredChunk],
    keyword_results: List[ScoredChunk],
    k: int = 60,
) -> List[ScoredChunk]:
    """Merge rankings from semantic and keyword search using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_score(chunk) = SUM( 1.0 / (k + rank_i) )
    """
    scores: Dict[int, float] = {}
    items: Dict[int, ScoredChunk] = {}

    # Accumulate semantic ranks (1-based)
    for rank, item in enumerate(semantic_results, start=1):
        chunk_id = item.chunk.id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        items[chunk_id] = item

    # Accumulate keyword ranks (1-based)
    for rank, item in enumerate(keyword_results, start=1):
        chunk_id = item.chunk.id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        if chunk_id not in items:
            items[chunk_id] = item

    # Sort items by merged RRF score descending
    sorted_chunk_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    merged: List[ScoredChunk] = []
    for cid in sorted_chunk_ids:
        original = items[cid]
        merged.append(
            ScoredChunk(
                chunk=original.chunk,
                document=original.document,
                score=round(scores[cid], 5),
            )
        )

    return merged


def deduplicate_results_by_document(
    results: List[ScoredChunk],
    max_per_document: int = 3,
) -> List[ScoredChunk]:
    """Cap maximum passages from any single document to prevent list flooding."""
    doc_counts: Dict[int, int] = {}
    deduped: List[ScoredChunk] = []

    for item in results:
        doc_id = item.document.id
        count = doc_counts.get(doc_id, 0)
        if count < max_per_document:
            deduped.append(item)
            doc_counts[doc_id] = count + 1

    return deduped


def _compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def execute_semantic_search(
    query: str,
    user_id: int,
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    document_ids: Optional[List[int]] = None,
    candidate_limit: int = 50,
) -> List[ScoredChunk]:
    """Execute cosine similarity vector search scoped strictly to user_id."""
    query_vector = await embedding_provider.embed_query(query)

    is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False

    base_filter = [Chunk.user_id == user_id]
    if document_ids:
        base_filter.append(Chunk.document_id.in_(document_ids))

    if is_postgres:
        # Native pgvector cosine distance search
        distance_col = Chunk.embedding.cosine_distance(query_vector)
        stmt = (
            select(Chunk, Document, distance_col.label("distance"))
            .join(Document, Chunk.document_id == Document.id)
            .where(*base_filter, Chunk.embedding.is_not(None))
            .order_by(distance_col.asc())
            .limit(candidate_limit)
        )
        res = await db.execute(stmt)
        items: List[ScoredChunk] = []
        for chunk, doc, dist in res.all():
            similarity = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
            items.append(ScoredChunk(chunk=chunk, document=doc, score=round(similarity, 4)))
        return items

    else:
        # Fallback for SQLite/in-memory test execution
        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(*base_filter)
        )
        res = await db.execute(stmt)
        candidates: List[ScoredChunk] = []
        for chunk, doc in res.all():
            if chunk.embedding:
                sim = _compute_cosine_similarity(query_vector, chunk.embedding)
                candidates.append(ScoredChunk(chunk=chunk, document=doc, score=round(sim, 4)))

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:candidate_limit]


async def execute_keyword_search(
    query: str,
    user_id: int,
    db: AsyncSession,
    document_ids: Optional[List[int]] = None,
    candidate_limit: int = 50,
) -> List[ScoredChunk]:
    """Execute full-text keyword search scoped strictly to user_id."""
    clean_query = query.strip()
    if not clean_query:
        return []

    is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False

    base_filter = [Chunk.user_id == user_id]
    if document_ids:
        base_filter.append(Chunk.document_id.in_(document_ids))

    if is_postgres:
        ts_query = func.plainto_tsquery("english", clean_query)
        rank_expr = func.ts_rank(Chunk.tsv, ts_query)

        stmt = (
            select(Chunk, Document, rank_expr.label("rank"))
            .join(Document, Chunk.document_id == Document.id)
            .where(*base_filter, Chunk.tsv.op("@@")(ts_query))
            .order_by(desc("rank"))
            .limit(candidate_limit)
        )
        res = await db.execute(stmt)
        items: List[ScoredChunk] = []
        for chunk, doc, rank_score in res.all():
            items.append(
                ScoredChunk(
                    chunk=chunk,
                    document=doc,
                    score=round(float(rank_score or 0.0), 4),
                )
            )
        return items

    else:
        # Fallback for SQLite/in-memory test execution
        query_words = [w.lower() for w in clean_query.split() if len(w) > 1]
        if not query_words:
            query_words = [clean_query.lower()]

        stmt = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(*base_filter)
        )
        res = await db.execute(stmt)

        candidates: List[ScoredChunk] = []
        for chunk, doc in res.all():
            content_lower = chunk.content.lower()
            # Calculate word match ratio
            matches = sum(1 for w in query_words if w in content_lower)
            if matches > 0:
                match_score = round(matches / len(query_words), 4)
                candidates.append(ScoredChunk(chunk=chunk, document=doc, score=match_score))

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:candidate_limit]


async def search_user_chunks(
    query: str,
    user_id: int,
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    mode: SearchMode = SearchMode.HYBRID,
    k: int = 60,
    limit: int = 10,
    document_ids: Optional[List[int]] = None,
    max_per_document: int = 3,
) -> List[SearchResultItem]:
    """Orchestrate search across semantic, keyword, or hybrid modes with de-duplication."""
    clean_query = query.strip()
    if not clean_query:
        return []

    if mode == SearchMode.SEMANTIC:
        raw_results = await execute_semantic_search(
            clean_query, user_id, db, embedding_provider, document_ids, candidate_limit=limit * 2
        )
    elif mode == SearchMode.KEYWORD:
        raw_results = await execute_keyword_search(
            clean_query, user_id, db, document_ids, candidate_limit=limit * 2
        )
    else:  # HYBRID
        semantic_results = await execute_semantic_search(
            clean_query, user_id, db, embedding_provider, document_ids, candidate_limit=limit * 3
        )
        keyword_results = await execute_keyword_search(
            clean_query, user_id, db, document_ids, candidate_limit=limit * 3
        )
        raw_results = compute_reciprocal_rank_fusion(
            semantic_results, keyword_results, k=k
        )

    # De-duplicate to prevent document flooding
    deduped = deduplicate_results_by_document(raw_results, max_per_document=max_per_document)
    final_items = deduped[:limit]

    return [
        SearchResultItem(
            chunk_id=item.chunk.id,
            document_id=item.document.id,
            document_title=item.document.title,
            source_type=item.document.source_type,
            page_number=item.chunk.page_number,
            snippet=item.chunk.content,
            score=item.score,
            chunk_index=item.chunk.chunk_index,
        )
        for item in final_items
    ]
