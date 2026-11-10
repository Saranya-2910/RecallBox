"""Tests for document intake: PDF upload, links, notes, duplicate detection, and user isolation."""
import io
import os

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.user import User

# Helper valid minimal PDF bytes
VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF"


@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient, test_user_auth_headers: dict):
    """Verify uploading a valid PDF succeeds and returns status=pending."""
    files = {"file": ("sample.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    data = {"title": "Sample PDF Document", "category": "engineering"}

    response = await client.post(
        "/documents/upload",
        files=files,
        data=data,
        headers=test_user_auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED

    doc = response.json()
    assert doc["title"] == "Sample PDF Document"
    assert doc["source_type"] == "pdf"
    assert doc["status"] == "pending"
    assert doc["category"] == "engineering"
    assert doc["file_path"] is not None
    assert os.path.exists(doc["file_path"])


@pytest.mark.asyncio
async def test_upload_non_pdf_extension_rejected(client: AsyncClient, test_user_auth_headers: dict):
    """Verify non-PDF file extensions are rejected with 400 Bad Request."""
    files = {"file": ("malicious.exe", io.BytesIO(b"executable content"), "application/octet-stream")}
    response = await client.post(
        "/documents/upload",
        files=files,
        headers=test_user_auth_headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Only PDF files" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_spoofed_pdf_header_rejected(client: AsyncClient, test_user_auth_headers: dict):
    """Verify files renamed to .pdf without valid %PDF- magic header are rejected."""
    files = {"file": ("fake.pdf", io.BytesIO(b"Plain text masquerading as PDF"), "application/pdf")}
    response = await client.post(
        "/documents/upload",
        files=files,
        headers=test_user_auth_headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid file format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(
    client: AsyncClient, test_user_auth_headers: dict, monkeypatch
):
    """Verify uploads exceeding configured MAX_UPLOAD_SIZE_MB are rejected with 413."""
    # Temporarily set max upload to 1MB for this test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)

    # 1.5 MB fake PDF data
    oversized_data = b"%PDF-1.4\n" + (b"0" * (1500 * 1024))
    files = {"file": ("large.pdf", io.BytesIO(oversized_data), "application/pdf")}

    response = await client.post(
        "/documents/upload",
        files=files,
        headers=test_user_auth_headers,
    )
    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "exceeds maximum upload size" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_pdf_duplicate_detection(client: AsyncClient, test_user_auth_headers: dict):
    """Verify uploading duplicate PDF content for the same user is rejected with 409."""
    files1 = {"file": ("doc.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res1 = await client.post("/documents/upload", files=files1, headers=test_user_auth_headers)
    assert res1.status_code == status.HTTP_201_CREATED

    files2 = {"file": ("doc_copy.pdf", io.BytesIO(VALID_PDF_BYTES), "application/pdf")}
    res2 = await client.post("/documents/upload", files=files2, headers=test_user_auth_headers)
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_create_link_document_success(client: AsyncClient, test_user_auth_headers: dict):
    """Verify creating a link document succeeds with status=pending."""
    payload = {
        "url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
        "title": "FastAPI Dependency Injection Tutorial",
        "category": "backend",
    }
    response = await client.post("/documents/link", json=payload, headers=test_user_auth_headers)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["source_type"] == "link"
    assert data["status"] == "pending"
    assert data["source_url"] == payload["url"]
    assert data["title"] == payload["title"]


@pytest.mark.asyncio
async def test_create_link_document_duplicate_rejected(client: AsyncClient, test_user_auth_headers: dict):
    """Verify submitting duplicate URLs for the same user is rejected with 409."""
    payload = {"url": "https://example.com/unique-article"}
    res1 = await client.post("/documents/link", json=payload, headers=test_user_auth_headers)
    assert res1.status_code == status.HTTP_201_CREATED

    res2 = await client.post("/documents/link", json=payload, headers=test_user_auth_headers)
    assert res2.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_create_note_document_success(client: AsyncClient, test_user_auth_headers: dict):
    """Verify storing a note saves content and returns status=pending."""
    payload = {
        "title": "Architecture Notes",
        "content": "RecallBox uses PostgreSQL with pgvector for hybrid retrieval.",
        "category": "notes",
    }
    response = await client.post("/documents/note", json=payload, headers=test_user_auth_headers)
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["source_type"] == "note"
    assert data["status"] == "pending"
    assert data["title"] == "Architecture Notes"
    assert data["file_path"] is not None
    assert os.path.exists(data["file_path"])


@pytest.mark.asyncio
async def test_list_documents_pagination_and_filtering(
    client: AsyncClient, test_user_auth_headers: dict
):
    """Verify listing documents supports pagination and category filtering."""
    # Create notes under different categories
    for i in range(5):
        await client.post(
            "/documents/note",
            json={"title": f"Work Note {i}", "content": f"Content {i}", "category": "work"},
            headers=test_user_auth_headers,
        )
    for i in range(3):
        await client.post(
            "/documents/note",
            json={"title": f"Personal Note {i}", "content": f"Personal {i}", "category": "personal"},
            headers=test_user_auth_headers,
        )

    # List all
    res_all = await client.get("/documents?limit=10", headers=test_user_auth_headers)
    assert res_all.status_code == status.HTTP_200_OK
    assert res_all.json()["total"] == 8

    # Filter by category
    res_work = await client.get("/documents?category=work", headers=test_user_auth_headers)
    assert res_work.status_code == status.HTTP_200_OK
    assert res_work.json()["total"] == 5

    # Test pagination
    res_page = await client.get("/documents?page=2&limit=3", headers=test_user_auth_headers)
    assert res_page.status_code == status.HTTP_200_OK
    data = res_page.json()
    assert data["page"] == 2
    assert len(data["items"]) == 3
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_user_isolation_document_access_and_deletion(
    client: AsyncClient, db_session: AsyncSession
):
    """Verify User A cannot list, view, or delete User B's documents."""
    user_a = User(email="usera_docs@example.com", password_hash=get_password_hash("passA12345!"))
    user_b = User(email="userb_docs@example.com", password_hash=get_password_hash("passB12345!"))
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    headers_a = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_a.id)})}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_b.id)})}"}

    # User A creates a document
    create_res = await client.post(
        "/documents/note",
        json={"title": "User A Secret Note", "content": "Confidential A"},
        headers=headers_a,
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    doc_a_id = create_res.json()["id"]
    file_path_a = create_res.json()["file_path"]

    # User B lists documents -> User A's document must NOT appear
    list_b = await client.get("/documents", headers=headers_b)
    assert list_b.status_code == status.HTTP_200_OK
    assert list_b.json()["total"] == 0

    # User B tries to get User A's document detail -> 404 Not Found
    get_b = await client.get(f"/documents/{doc_a_id}", headers=headers_b)
    assert get_b.status_code == status.HTTP_404_NOT_FOUND

    # User B tries to delete User A's document -> 404 Not Found
    del_b = await client.delete(f"/documents/{doc_a_id}", headers=headers_b)
    assert del_b.status_code == status.HTTP_404_NOT_FOUND

    # Document and file must still exist
    assert os.path.exists(file_path_a)

    # User A can get their own document
    get_a = await client.get(f"/documents/{doc_a_id}", headers=headers_a)
    assert get_a.status_code == status.HTTP_200_OK

    # User A deletes their own document -> 204 No Content
    del_a = await client.delete(f"/documents/{doc_a_id}", headers=headers_a)
    assert del_a.status_code == status.HTTP_204_NO_CONTENT

    # File must be deleted from storage
    assert not os.path.exists(file_path_a)

    # Subsequent GET returns 404
    get_a_deleted = await client.get(f"/documents/{doc_a_id}", headers=headers_a)
    assert get_a_deleted.status_code == status.HTTP_404_NOT_FOUND
