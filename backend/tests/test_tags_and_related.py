"""Tests for Phase 7 organisation features: automated summarization, tags, and related documents."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.tag import Tag
from app.models.user import User
from app.schemas.document import DocumentStatus, SourceType
from app.services.embedding import MockEmbeddingProvider
from app.services.ingestion import ingest_document
from app.services.llm import MockLLMProvider
from app.services.storage import LocalStorageService


@pytest.mark.asyncio
async def test_ready_document_has_summary_and_tags(
    db_session: AsyncSession,
    test_user: User,
    test_storage: LocalStorageService,
):
    """Acceptance criterion: Each ready document has a summary and tags."""
    content = "FastAPI uses modern Python type annotations to generate OpenAPI specifications and validate requests."
    file_path = await test_storage.save_file(content.encode("utf-8"), "fastapi_overview.txt", test_user.id)

    doc = Document(
        user_id=test_user.id,
        title="FastAPI Overview",
        source_type=SourceType.NOTE.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    mock_emb = MockEmbeddingProvider()
    mock_llm = MockLLMProvider()

    # Ingest document
    ready_doc = await ingest_document(
        document_id=doc.id,
        db=db_session,
        storage=test_storage,
        embedding_provider=mock_emb,
        llm_provider=mock_llm,
    )

    assert ready_doc.status == DocumentStatus.READY.value
    assert ready_doc.summary is not None
    assert len(ready_doc.summary) > 10
    assert len(ready_doc.tags) >= 2
    tag_names = [t.name for t in ready_doc.tags]
    assert "fastapi" in tag_names or "python" in tag_names


@pytest.mark.asyncio
async def test_fail_soft_summarization(
    db_session: AsyncSession,
    test_user: User,
    test_storage: LocalStorageService,
):
    """Acceptance criterion: If summarization fails, document is still ready and searchable."""
    content = "Resilient distributed systems must handle partial external service failures gracefully."
    file_path = await test_storage.save_file(content.encode("utf-8"), "resilience.txt", test_user.id)

    doc = Document(
        user_id=test_user.id,
        title="Distributed Systems",
        source_type=SourceType.NOTE.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    # Broken LLM provider that simulates outage
    def broken_responder(prompt, system_instruction):
        raise ConnectionError("LLM service unavailable")

    broken_llm = MockLLMProvider(custom_responder=broken_responder)
    mock_emb = MockEmbeddingProvider()

    # Ingestion must not crash and document must reach ready status
    ready_doc = await ingest_document(
        document_id=doc.id,
        db=db_session,
        storage=test_storage,
        embedding_provider=mock_emb,
        llm_provider=broken_llm,
    )

    assert ready_doc.status == DocumentStatus.READY.value
    assert ready_doc.error is None  # Document ingestion itself succeeded


@pytest.mark.asyncio
async def test_tag_management_endpoints(
    client: AsyncClient,
    test_user: User,
    test_user_auth_headers: dict,
    db_session: AsyncSession,
):
    """Verify manual tag creation, listing, and deletion on documents."""
    doc = Document(
        user_id=test_user.id,
        title="Tag Test Document",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    # Add tag to document
    add_res = await client.post(
        f"/documents/{doc.id}/tags",
        json={"name": "backend-infra"},
        headers=test_user_auth_headers,
    )
    assert add_res.status_code == 201
    tag_id = add_res.json()["id"]
    assert add_res.json()["name"] == "backend-infra"

    # List user tags
    list_res = await client.get("/tags", headers=test_user_auth_headers)
    assert list_res.status_code == 200
    tags = list_res.json()
    assert any(t["name"] == "backend-infra" for t in tags)

    # Remove tag from document
    del_res = await client.delete(
        f"/documents/{doc.id}/tags/{tag_id}",
        headers=test_user_auth_headers,
    )
    assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_tag_filter_on_get_documents(
    client: AsyncClient,
    test_user: User,
    test_user_auth_headers: dict,
    db_session: AsyncSession,
):
    """Acceptance criterion: Tag filters work on GET /documents."""
    tag_py = Tag(user_id=test_user.id, name="python")
    tag_db = Tag(user_id=test_user.id, name="database")
    db_session.add_all([tag_py, tag_db])
    await db_session.flush()

    doc1 = Document(
        user_id=test_user.id,
        title="Python Guide",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
        tags=[tag_py],
    )
    doc2 = Document(
        user_id=test_user.id,
        title="PostgreSQL Guide",
        source_type=SourceType.NOTE.value,
        status=DocumentStatus.READY.value,
        tags=[tag_db],
    )
    db_session.add_all([doc1, doc2])
    await db_session.commit()

    # Filter by tag=python
    res_py = await client.get("/documents?tag=python", headers=test_user_auth_headers)
    assert res_py.status_code == 200
    data_py = res_py.json()
    assert data_py["total"] == 1
    assert data_py["items"][0]["title"] == "Python Guide"

    # Filter by tag=database
    res_db = await client.get("/documents?tag=database", headers=test_user_auth_headers)
    assert res_db.status_code == 200
    data_db = res_db.json()
    assert data_db["total"] == 1
    assert data_db["items"][0]["title"] == "PostgreSQL Guide"


@pytest.mark.asyncio
async def test_related_documents_endpoint_and_user_isolation(
    client: AsyncClient,
    test_user: User,
    test_user_auth_headers: dict,
    db_session: AsyncSession,
):
    """Acceptance criterion: Related endpoint returns sensible neighbours with user isolation."""
    mock_emb = MockEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)

    # Document 1: Python Web Frameworks
    doc1 = Document(user_id=test_user.id, title="FastAPI Framework", source_type="note", status="ready")
    # Document 2: Async Python Web Services (similar to Doc 1)
    doc2 = Document(user_id=test_user.id, title="Async Python APIs", source_type="note", status="ready")
    # Document 3: Indoor Gardening (distant from Doc 1)
    doc3 = Document(user_id=test_user.id, title="Indoor Houseplants", source_type="note", status="ready")
    db_session.add_all([doc1, doc2, doc3])
    await db_session.commit()
    await db_session.refresh(doc1)
    await db_session.refresh(doc2)
    await db_session.refresh(doc3)

    # Chunks and embeddings
    text1 = "FastAPI web framework building async REST APIs in Python."
    text2 = "Async Python APIs and HTTP services using asynchronous frameworks."
    text3 = "Watering indoor houseplants and providing proper sunlight in gardens."

    emb1 = (await mock_emb.embed_texts([text1]))[0]
    emb2 = (await mock_emb.embed_texts([text2]))[0]
    emb3 = (await mock_emb.embed_texts([text3]))[0]

    chunk1 = Chunk(document_id=doc1.id, user_id=test_user.id, chunk_index=0, content=text1, embedding=emb1)
    chunk2 = Chunk(document_id=doc2.id, user_id=test_user.id, chunk_index=0, content=text2, embedding=emb2)
    chunk3 = Chunk(document_id=doc3.id, user_id=test_user.id, chunk_index=0, content=text3, embedding=emb3)
    db_session.add_all([chunk1, chunk2, chunk3])
    await db_session.commit()

    # Query related for Doc 1
    response = await client.get(f"/documents/{doc1.id}/related", headers=test_user_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc1.id
    assert len(data["related"]) == 2

    # Verify Doc 1 is not in its own related list
    related_ids = [r["document_id"] for r in data["related"]]
    assert doc1.id not in related_ids

    # User isolation: User B cannot access Doc 1's related documents
    user_b = User(email="intruder_rel@example.com", password_hash=get_password_hash("pass123!"))
    db_session.add(user_b)
    await db_session.commit()
    await db_session.refresh(user_b)

    headers_b = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_b.id)})}"}
    res_b = await client.get(f"/documents/{doc1.id}/related", headers=headers_b)
    assert res_b.status_code == 404
