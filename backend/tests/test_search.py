"""Tests for Phase 5 search service: semantic, keyword, and hybrid RRF search."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentStatus, SourceType
from app.services.embedding import MockEmbeddingProvider
from app.services.search import (
    ScoredChunk,
    compute_reciprocal_rank_fusion,
    deduplicate_results_by_document,
)


@pytest.fixture
async def search_corpus_user(
    db_session: AsyncSession,
) -> User:
    """Create a user with indexed chunks covering diverse technical topics."""
    user = User(
        email="searcher@example.com",
        password_hash=get_password_hash("password123!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc1 = Document(
        user_id=user.id,
        title="FastAPI Architecture Guide",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
    )
    doc2 = Document(
        user_id=user.id,
        title="PostgreSQL Indexing Strategies",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
    )
    doc3 = Document(
        user_id=user.id,
        title="Redis Caching Patterns",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
    )
    db_session.add_all([doc1, doc2, doc3])
    await db_session.commit()
    await db_session.refresh(doc1)
    await db_session.refresh(doc2)
    await db_session.refresh(doc3)

    mock_emb = MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)

    c1_text = "FastAPI dependency injection enables clean parameter decoupling and modular software architecture in modern Python web services."
    c2_text = "PostgreSQL uses B-Tree indexes for equality, GIN indexes for tsvector full-text search, and HNSW for pgvector similarity."
    c3_text = "Redis caching reduces database read pressure using write-through and cache-aside patterns with strict TTL expirations."

    emb1 = (await mock_emb.embed_texts([c1_text]))[0]
    emb2 = (await mock_emb.embed_texts([c2_text]))[0]
    emb3 = (await mock_emb.embed_texts([c3_text]))[0]

    chunk1 = Chunk(
        document_id=doc1.id,
        user_id=user.id,
        chunk_index=0,
        content=c1_text,
        page_number=1,
        embedding=emb1,
    )
    chunk2 = Chunk(
        document_id=doc2.id,
        user_id=user.id,
        chunk_index=0,
        content=c2_text,
        page_number=1,
        embedding=emb2,
    )
    chunk3 = Chunk(
        document_id=doc3.id,
        user_id=user.id,
        chunk_index=0,
        content=c3_text,
        page_number=1,
        embedding=emb3,
    )
    db_session.add_all([chunk1, chunk2, chunk3])
    await db_session.commit()

    return user


# ---------------------------------------------------------------------------
# Unit tests: RRF and De-duplication Logic
# ---------------------------------------------------------------------------


def test_reciprocal_rank_fusion_math():
    """Verify RRF formula assigns correct combined scores."""
    # Chunk A: rank 1 in semantic, rank 2 in keyword
    # Chunk B: rank 2 in semantic, rank 1 in keyword
    # Chunk C: rank 3 in semantic only
    dummy_doc = Document(id=1, title="Doc 1", source_type="note")
    chunk_a = Chunk(id=101, document_id=1, user_id=1, chunk_index=0, content="Chunk A")
    chunk_b = Chunk(id=102, document_id=1, user_id=1, chunk_index=1, content="Chunk B")
    chunk_c = Chunk(id=103, document_id=1, user_id=1, chunk_index=2, content="Chunk C")

    sem_list = [
        ScoredChunk(chunk=chunk_a, document=dummy_doc, score=0.9),
        ScoredChunk(chunk=chunk_b, document=dummy_doc, score=0.8),
        ScoredChunk(chunk=chunk_c, document=dummy_doc, score=0.7),
    ]

    kw_list = [
        ScoredChunk(chunk=chunk_b, document=dummy_doc, score=1.0),
        ScoredChunk(chunk=chunk_a, document=dummy_doc, score=0.5),
    ]

    k = 60
    fused = compute_reciprocal_rank_fusion(sem_list, kw_list, k=k)

    # Both A and B appeared at rank 1 & 2 across the lists, so:
    # score(A) = 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.016393 + 0.016129 = 0.03252
    # score(B) = 1/(60+2) + 1/(60+1) = 0.03252
    # score(C) = 1/(60+3) = 0.01587
    assert len(fused) == 3
    assert fused[0].chunk.id in [101, 102]
    assert fused[1].chunk.id in [101, 102]
    assert fused[2].chunk.id == 103
    assert fused[2].score < fused[0].score


def test_deduplicate_by_document_caps_representation():
    """Verify deduplication limits results per document."""
    doc1 = Document(id=1, title="Large Doc", source_type="pdf")
    doc2 = Document(id=2, title="Other Doc", source_type="note")

    results = [
        ScoredChunk(chunk=Chunk(id=1, document_id=1, user_id=1, chunk_index=0, content="c1"), document=doc1, score=0.9),
        ScoredChunk(chunk=Chunk(id=2, document_id=1, user_id=1, chunk_index=1, content="c2"), document=doc1, score=0.8),
        ScoredChunk(chunk=Chunk(id=3, document_id=1, user_id=1, chunk_index=2, content="c3"), document=doc1, score=0.7),
        ScoredChunk(chunk=Chunk(id=4, document_id=1, user_id=1, chunk_index=3, content="c4"), document=doc1, score=0.6),
        ScoredChunk(chunk=Chunk(id=5, document_id=2, user_id=1, chunk_index=0, content="c5"), document=doc2, score=0.5),
    ]

    deduped = deduplicate_results_by_document(results, max_per_document=2)
    # Doc 1 should only have 2 chunks, doc 2 should have 1 chunk (total 3)
    assert len(deduped) == 3
    doc1_items = [x for x in deduped if x.document.id == 1]
    doc2_items = [x for x in deduped if x.document.id == 2]
    assert len(doc1_items) == 2
    assert len(doc2_items) == 1


# ---------------------------------------------------------------------------
# Integration tests: GET /search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_modes_and_user_isolation(
    client: AsyncClient,
    search_corpus_user: User,
    db_session: AsyncSession,
):
    """Acceptance criterion: GET /search works in all 3 modes and respects user isolation."""
    token_a = create_access_token(data={"sub": str(search_corpus_user.id)})
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Semantic search
    res_sem = await client.get("/search?q=FastAPI+dependency&mode=semantic", headers=headers_a)
    assert res_sem.status_code == 200
    data_sem = res_sem.json()
    assert data_sem["mode"] == "semantic"
    assert data_sem["total_results"] > 0
    assert "FastAPI" in data_sem["results"][0]["snippet"]

    # 2. Keyword search
    res_kw = await client.get("/search?q=PostgreSQL+GIN&mode=keyword", headers=headers_a)
    assert res_kw.status_code == 200
    data_kw = res_kw.json()
    assert data_kw["mode"] == "keyword"
    assert data_kw["total_results"] > 0
    assert "PostgreSQL" in data_kw["results"][0]["snippet"]

    # 3. Hybrid search
    res_hyb = await client.get("/search?q=Redis+caching&mode=hybrid&k=60", headers=headers_a)
    assert res_hyb.status_code == 200
    data_hyb = res_hyb.json()
    assert data_hyb["mode"] == "hybrid"
    assert data_hyb["total_results"] > 0
    assert "Redis" in data_hyb["results"][0]["snippet"]

    # 4. User Isolation: Another user searching finds 0 results
    user_b = User(email="user_empty@example.com", password_hash=get_password_hash("pass123!"))
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)

    token_b = create_access_token(data={"sub": str(user_b.id)})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res_b = await client.get("/search?q=FastAPI&mode=hybrid", headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json()["total_results"] == 0
    assert res_b.json()["results"] == []


@pytest.mark.asyncio
async def test_search_empty_results_handling(
    client: AsyncClient,
    search_corpus_user: User,
):
    """Acceptance criterion: Tests empty-result handling gracefully."""
    token = create_access_token(data={"sub": str(search_corpus_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    # Query with no match
    res = await client.get("/search?q=QuantumSuperpositionGraviton&mode=keyword", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] == 0
    assert data["results"] == []


@pytest.mark.asyncio
async def test_paraphrased_query_finds_chunk(
    client: AsyncClient,
    search_corpus_user: User,
):
    """Acceptance criterion: A paraphrased query (semantic concept) finds the right chunk."""
    token = create_access_token(data={"sub": str(search_corpus_user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    # Query concepts for FastAPI chunk without exact sentence phrasing
    res = await client.get(
        "/search?q=modular+service+parameter+injection&mode=hybrid",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] > 0
    # Returns chunk matching the concept
    assert "FastAPI" in data["results"][0]["document_title"]
