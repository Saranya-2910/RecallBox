"""Tests for Phase 4 ingestion pipeline: extraction, chunking, embedding, and reprocessing."""
import io

import pytest
from httpx import AsyncClient
from pypdf import PageObject, PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentStatus, SourceType
from app.services.chunker import Chunker
from app.services.embedding import MockEmbeddingProvider
from app.services.extractor import ExtractedPage
from app.services.ingestion import ingest_document
from app.services.storage import LocalStorageService


def create_sample_pdf(num_pages: int = 20) -> bytes:
    """Generate in-memory valid PDF bytes with specified page count and text."""
    writer = PdfWriter()
    for i in range(1, num_pages + 1):
        # Create a blank letter-sized page
        page = PageObject.create_blank_page(width=612, height=792)
        writer.add_page(page)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit tests: Chunker
# ---------------------------------------------------------------------------


def test_chunking_empty_input():
    """Verify chunker returns empty list for empty pages list or whitespace text."""
    chunker = Chunker(target_chunk_size=600, overlap_tokens=90)
    assert chunker.chunk_pages([]) == []
    assert chunker.chunk_pages([ExtractedPage(content="   ", page_number=1)]) == []


def test_chunking_short_document():
    """Verify chunker returns a single chunk for content under target chunk size."""
    chunker = Chunker(target_chunk_size=600, overlap_tokens=90)
    text = "RecallBox is a personal knowledge base built with FastAPI and PostgreSQL pgvector."
    pages = [ExtractedPage(content=text, page_number=1)]

    chunks = chunker.chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1
    assert chunks[0].content == text
    assert chunks[0].token_count > 0


def test_chunking_long_document_sizes_and_overlap():
    """Verify long text produces multiple chunks respecting boundaries and carrying overlap."""
    chunker = Chunker(target_chunk_size=100, overlap_tokens=25)

    # Build 10 distinct paragraphs
    paragraphs = [
        f"Paragraph {i}: This is an in-depth explanation of system design and distributed retrieval mechanisms in modern artificial intelligence applications. Each paragraph adds several tokens."
        for i in range(1, 15)
    ]
    long_text = "\n\n".join(paragraphs)
    pages = [ExtractedPage(content=long_text, page_number=1)]

    chunks = chunker.chunk_pages(pages)
    assert len(chunks) > 1

    # Verify sequential chunk indexing and page numbers
    for idx, c in enumerate(chunks):
        assert c.chunk_index == idx
        assert c.page_number == 1

    # Verify overlap exists between consecutive chunks
    for i in range(len(chunks) - 1):
        c1_content = chunks[i].content
        c2_content = chunks[i + 1].content
        # The trailing lines/words of chunk i should appear in chunk i+1
        c1_words = c1_content.split()
        overlap_found = any(w in c2_content for w in c1_words[-5:])
        assert overlap_found, f"Expected token overlap between chunk {i} and {i+1}"


# ---------------------------------------------------------------------------
# Integration tests: Ingestion Pipeline & Worker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_20_page_pdf_ingestion_stores_chunks_and_embeddings(
    db_session: AsyncSession, test_user: User, test_storage: LocalStorageService
):
    """Acceptance criterion: Uploading a 20-page PDF ends with status=ready and chunks stored."""
    pdf_bytes = create_sample_pdf(num_pages=20)
    file_path = await test_storage.save_file(pdf_bytes, "twenty_pages.pdf", test_user.id)

    doc = Document(
        user_id=test_user.id,
        title="20 Page Technical Manual",
        source_type=SourceType.PDF.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    mock_embedding = MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)

    # Execute ingestion pipeline
    processed_doc = await ingest_document(
        document_id=doc.id,
        db=db_session,
        storage=test_storage,
        embedding_provider=mock_embedding,
    )

    assert processed_doc.status == DocumentStatus.READY.value
    assert processed_doc.error is None

    # Verify chunks stored in database
    stmt = select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
    result = await db_session.scalars(stmt)
    stored_chunks = list(result.all())

    assert len(stored_chunks) >= 1
    for chunk in stored_chunks:
        assert chunk.user_id == test_user.id
        assert chunk.document_id == doc.id
        assert chunk.embedding is not None
        assert len(chunk.embedding) == settings.EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_corrupted_pdf_ends_with_failed_status_without_crashing(
    db_session: AsyncSession, test_user: User, test_storage: LocalStorageService
):
    """Acceptance criterion: A corrupted PDF ends with status=failed and readable error."""
    corrupted_bytes = b"%PDF-1.4\ncorrupted binary payload that is completely invalid"
    file_path = await test_storage.save_file(corrupted_bytes, "corrupt.pdf", test_user.id)

    doc = Document(
        user_id=test_user.id,
        title="Corrupted Document",
        source_type=SourceType.PDF.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    mock_embedding = MockEmbeddingProvider()

    # Ingestion must catch error and set status to failed without raising unhandled crash
    processed_doc = await ingest_document(
        document_id=doc.id,
        db=db_session,
        storage=test_storage,
        embedding_provider=mock_embedding,
    )

    assert processed_doc.status == DocumentStatus.FAILED.value
    assert processed_doc.error is not None
    assert "Corrupted or invalid PDF" in processed_doc.error


@pytest.mark.asyncio
async def test_reprocess_endpoint_idempotency_and_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    test_user_auth_headers: dict,
    test_storage: LocalStorageService,
):
    """Verify POST /documents/{id}/reprocess replaces chunks idempotently and enforces isolation."""
    # Create note document
    note_content = "RecallBox utilizes pgvector and PostgreSQL full-text search for hybrid retrieval."
    note_path = await test_storage.save_file(note_content.encode("utf-8"), "test_note.txt", test_user.id)

    doc = Document(
        user_id=test_user.id,
        title="Reprocess Test Note",
        source_type=SourceType.NOTE.value,
        file_path=note_path,
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    # Initial reprocess
    res1 = await client.post(f"/documents/{doc.id}/reprocess", headers=test_user_auth_headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "ready"

    stmt = select(Chunk).where(Chunk.document_id == doc.id)
    chunks_round1 = (await db_session.scalars(stmt)).all()
    count_round1 = len(chunks_round1)
    assert count_round1 > 0

    # Second reprocess: verify old chunks are replaced, count does not double
    res2 = await client.post(f"/documents/{doc.id}/reprocess", headers=test_user_auth_headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "ready"

    chunks_round2 = (await db_session.scalars(stmt)).all()
    assert len(chunks_round2) == count_round1

    # Verify user isolation: another user cannot reprocess this document
    user_b = User(email="other_reprocess@example.com", password_hash=get_password_hash("pass12345!"))
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)

    headers_b = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_b.id)})}"}
    res_b = await client.post(f"/documents/{doc.id}/reprocess", headers=headers_b)
    assert res_b.status_code == 404
