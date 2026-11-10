"""Find related documents by comparing document-level average chunk embeddings."""
import math
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.related import RelatedDocumentItem


def _average_and_normalize(vectors: List[List[float]]) -> List[float]:
    """Compute centroid (average) vector and L2 normalize it."""
    if not vectors:
        return []
    dim = len(vectors[0])
    avg = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            avg[i] += v[i]

    count = len(vectors)
    for i in range(dim):
        avg[i] /= count

    norm = math.sqrt(sum(x * x for x in avg)) or 1.0
    return [x / norm for x in avg]


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two normalized vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))


async def find_related_documents(
    document_id: int,
    user_id: int,
    db: AsyncSession,
    limit: int = 5,
) -> List[RelatedDocumentItem]:
    """Retrieve semantically related documents for a target document within user's corpus."""
    # 1. Fetch target document chunks
    target_stmt = select(Chunk).where(
        Chunk.document_id == document_id,
        Chunk.user_id == user_id,
    )
    target_chunks = (await db.scalars(target_stmt)).all()
    target_embeddings = [c.embedding for c in target_chunks if c.embedding]

    if not target_embeddings:
        return []

    target_vector = _average_and_normalize(target_embeddings)

    # 2. Fetch candidate chunks from other documents belonging to the user
    cand_stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.user_id == user_id,
            Chunk.document_id != document_id,
        )
    )
    result = await db.execute(cand_stmt)

    docs_map: Dict[int, Document] = {}
    doc_vectors_map: Dict[int, List[List[float]]] = {}

    for chunk, doc in result.all():
        if chunk.embedding:
            docs_map[doc.id] = doc
            doc_vectors_map.setdefault(doc.id, []).append(chunk.embedding)

    scored_candidates: List[RelatedDocumentItem] = []
    for doc_id, doc in docs_map.items():
        embeddings = doc_vectors_map.get(doc_id, [])
        if not embeddings:
            continue
        doc_avg_vector = _average_and_normalize(embeddings)
        sim = _cosine_similarity(target_vector, doc_avg_vector)

        scored_candidates.append(
            RelatedDocumentItem(
                document_id=doc.id,
                title=doc.title,
                source_type=doc.source_type,
                summary=doc.summary,
                category=doc.category,
                similarity=round(sim, 4),
            )
        )

    # Sort descending by similarity
    scored_candidates.sort(key=lambda x: x.similarity, reverse=True)
    return scored_candidates[:limit]
