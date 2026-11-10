"""Tests for Phase 6 Cited Question Answering (RAG): grounding, citations, and logging."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.qa_log import QALog
from app.models.user import User
from app.schemas.document import DocumentStatus, SourceType
from app.schemas.search import SearchResultItem
from app.services.embedding import MockEmbeddingProvider
from app.services.qa import extract_and_validate_citations


@pytest.fixture
async def rag_user_with_document(
    db_session: AsyncSession,
) -> User:
    """Create a user with an indexed document and chunk for RAG testing."""
    user = User(
        email="rag_student@example.com",
        password_hash=get_password_hash("password123!"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    doc = Document(
        user_id=user.id,
        title="FastAPI Dependency Injection Guide",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    mock_emb = MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    content = "FastAPI uses standard Python type hints for dependency injection with Depends()."
    emb = (await mock_emb.embed_texts([content]))[0]

    chunk = Chunk(
        document_id=doc.id,
        user_id=user.id,
        chunk_index=0,
        content=content,
        page_number=1,
        embedding=emb,
    )
    db_session.add(chunk)
    await db_session.commit()
    await db_session.refresh(chunk)

    return user


# ---------------------------------------------------------------------------
# Unit tests: Citation Extraction and Hallucination Filtering
# ---------------------------------------------------------------------------


def test_citation_validation_drops_hallucinated_ids():
    """Acceptance criterion: Verify citation validator drops IDs not in retrieved set."""
    retrieved = [
        SearchResultItem(
            chunk_id=101,
            document_id=1,
            document_title="Doc 1",
            source_type="note",
            page_number=1,
            snippet="Chunk 101 snippet",
            score=0.9,
            chunk_index=0,
        ),
        SearchResultItem(
            chunk_id=102,
            document_id=1,
            document_title="Doc 1",
            source_type="note",
            page_number=2,
            snippet="Chunk 102 snippet",
            score=0.8,
            chunk_index=1,
        ),
    ]

    # LLM output cites valid chunk 101, valid chunk 102, and hallucinated chunk 999
    llm_output = (
        "According to [Chunk 101], the system scales well. "
        "Furthermore, [Chunk 999] states that it uses quantum computing, "
        "and [Chunk 102] mentions persistent storage."
    )

    valid_citations, valid_ids = extract_and_validate_citations(llm_output, retrieved)

    # Hallucinated ID 999 must be dropped
    assert 999 not in valid_ids
    assert len(valid_citations) == 2
    assert valid_ids == [101, 102]
    assert valid_citations[0].chunk_id == 101
    assert valid_citations[1].chunk_id == 102


# ---------------------------------------------------------------------------
# Integration tests: POST /ask
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_answerable_question_returns_citations_and_logs(
    client: AsyncClient,
    rag_user_with_document: User,
    db_session: AsyncSession,
):
    """Acceptance criterion: Answerable question returns correct answer with valid citation."""
    token = create_access_token(data={"sub": str(rag_user_with_document.id)})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"question": "How does FastAPI manage dependency injection?"}
    response = await client.post("/ask", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "question" in data
    assert "answer" in data
    assert len(data["citations"]) >= 1

    citation = data["citations"][0]
    assert citation["document_title"] == "FastAPI Dependency Injection Guide"
    assert "FastAPI" in citation["snippet"]
    assert citation["page_number"] == 1

    # Verify audit log in qa_logs database table
    qa_log_id = data["qa_log_id"]
    assert qa_log_id is not None

    stmt = select(QALog).where(QALog.id == qa_log_id)
    log_entry = await db_session.scalar(stmt)
    assert log_entry is not None
    assert log_entry.user_id == rag_user_with_document.id
    assert len(log_entry.cited_chunk_ids) >= 1


@pytest.mark.asyncio
async def test_ask_unanswerable_question_returns_explicit_refusal(
    client: AsyncClient,
    rag_user_with_document: User,
):
    """Acceptance criterion: Asking something not in documents returns 'not found in your saved material'."""
    token = create_access_token(data={"sub": str(rag_user_with_document.id)})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"question": "What is the secret recipe for Martian soup? NOT_FOUND_TRIGGER"}
    response = await client.post("/ask", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "not found in your saved material" in data["answer"].lower()
    assert data["citations"] == []


@pytest.mark.asyncio
async def test_ask_enforces_user_isolation(
    client: AsyncClient,
    rag_user_with_document: User,
    db_session: AsyncSession,
):
    """Verify User B cannot query or obtain citations from User A's documents."""
    user_b = User(email="intruder@example.com", password_hash=get_password_hash("pass123!"))
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)

    token_b = create_access_token(data={"sub": str(user_b.id)})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    payload = {"question": "How does FastAPI manage dependency injection?"}
    response = await client.post("/ask", json=payload, headers=headers_b)
    assert response.status_code == 200

    data = response.json()
    # User B has no documents, so no chunks are found
    assert data["citations"] == []
    assert "not found in your saved material" in data["answer"].lower()
