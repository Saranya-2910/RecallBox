"""Document intake endpoints: PDF upload, links, notes, pagination, filtering, deletion, reprocessing, and related."""
import hashlib
import logging
import math
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security_ssrf import SSRFValidationError, validate_url_safe
from app.db.session import get_db
from app.models.document import Document
from app.models.tag import Tag
from app.models.user import User
from app.schemas.document import (
    CreateLinkRequest,
    CreateNoteRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    SourceType,
)
from app.schemas.related import RelatedDocumentsResponse
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.ingestion import ingest_document
from app.services.related import find_related_documents
from app.services.storage import StorageService, get_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _enqueue_ingestion(document_id: int) -> None:
    """Dispatch background Celery ingestion task unless running in test mode."""
    if settings.APP_ENV == "testing":
        return
    try:
        from app.workers.celery_app import process_document_task
        process_document_task.delay(document_id)
    except Exception as exc:
        logger.warning(
            "Failed to enqueue Celery ingestion task for document id=%d: %s",
            document_id,
            exc,
        )


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload PDF document",
)
async def upload_pdf_document(
    file: UploadFile = File(..., description="PDF file binary"),
    title: Optional[str] = Form(None, description="Optional document title override"),
    category: Optional[str] = Form(None, description="Optional classification category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """Accept and store a PDF document, enforcing size limits and duplicate checks."""
    filename = file.filename or "uploaded.pdf"

    # Enforce PDF extension
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files (.pdf) are supported",
        )

    # Read binary content
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()

    # Enforce size limit
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Validate PDF magic header (%PDF-)
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format: Not a valid PDF binary",
        )

    # Compute SHA-256 content hash for duplicate detection
    content_hash = hashlib.sha256(content).hexdigest()

    # Check for existing duplicate document in the current user's library
    dup_stmt = select(Document).where(
        Document.user_id == current_user.id,
        Document.content_hash == content_hash,
    )
    existing_doc = await db.scalar(dup_stmt)
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document with identical content already exists (ID: {existing_doc.id})",
        )

    # Determine document title
    doc_title = title.strip() if title and title.strip() else filename.rsplit(".", 1)[0]

    # Save to storage
    file_path = await storage.save_file(content, filename, current_user.id)

    # Create document row with status=pending
    document = Document(
        user_id=current_user.id,
        title=doc_title,
        source_type=SourceType.PDF.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
        category=category.strip() if category and category.strip() else None,
        content_hash=content_hash,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    _enqueue_ingestion(document.id)
    logger.info("PDF document id=%d intake complete with status=pending", document.id)
    return document


@router.post(
    "/link",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save web article link",
)
async def create_link_document(
    payload: CreateLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Intake an external URL link for asynchronous extraction and indexing."""
    url_str = str(payload.url).strip()

    # SSRF Protection: validate scheme, hostname, and target IP address
    try:
        url_str = validate_url_safe(url_str)
    except SSRFValidationError as e:
        logger.warning("SSRF validation failed for link submission '%s': %s", url_str, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or prohibited URL: {e}",
        )

    content_hash = hashlib.sha256(url_str.encode("utf-8")).hexdigest()

    # Duplicate check for this user
    dup_stmt = select(Document).where(
        Document.user_id == current_user.id,
        Document.content_hash == content_hash,
    )
    existing_doc = await db.scalar(dup_stmt)
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Link with identical URL already exists (ID: {existing_doc.id})",
        )

    title = payload.title.strip() if payload.title and payload.title.strip() else url_str

    document = Document(
        user_id=current_user.id,
        title=title,
        source_type=SourceType.LINK.value,
        source_url=url_str,
        status=DocumentStatus.PENDING.value,
        category=payload.category.strip() if payload.category and payload.category.strip() else None,
        content_hash=content_hash,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    _enqueue_ingestion(document.id)
    logger.info("Link document id=%d intake complete with status=pending", document.id)
    return document


@router.post(
    "/note",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save plain text or markdown note",
)
async def create_note_document(
    payload: CreateNoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """Store user notes directly on storage and record database entry."""
    note_content = payload.content.strip()
    content_bytes = note_content.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Duplicate check for this user
    dup_stmt = select(Document).where(
        Document.user_id == current_user.id,
        Document.content_hash == content_hash,
    )
    existing_doc = await db.scalar(dup_stmt)
    if existing_doc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Note with identical content already exists (ID: {existing_doc.id})",
        )

    # Save note text to storage
    file_path = await storage.save_file(content_bytes, f"{payload.title}.txt", current_user.id)

    document = Document(
        user_id=current_user.id,
        title=payload.title.strip(),
        source_type=SourceType.NOTE.value,
        file_path=file_path,
        status=DocumentStatus.PENDING.value,
        category=payload.category.strip() if payload.category and payload.category.strip() else None,
        content_hash=content_hash,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    _enqueue_ingestion(document.id)
    logger.info("Note document id=%d intake complete with status=pending", document.id)
    return document


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter user documents with pagination and tags",
)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status (pending, processing, ready, failed)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tag: Optional[str] = Query(None, description="Filter by associated tag name"),
    source_type: Optional[str] = Query(None, description="Filter by source_type (pdf, link, note)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """Retrieve user's documents scoped strictly to their account with optional filters."""
    base_filter = [Document.user_id == current_user.id]

    if status:
        base_filter.append(Document.status == status.lower())
    if category:
        base_filter.append(Document.category == category)
    if source_type:
        base_filter.append(Document.source_type == source_type.lower())
    if tag:
        clean_tag = tag.lower().strip()
        base_filter.append(Document.tags.any(Tag.name == clean_tag))

    # Count total matching
    count_stmt = select(func.count(Document.id.distinct())).where(*base_filter)
    total = (await db.scalar(count_stmt)) or 0

    # Query items with pagination
    offset = (page - 1) * limit
    items_stmt = (
        select(Document)
        .where(*base_filter)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.scalars(items_stmt)
    items = list(result.all())

    pages = math.ceil(total / limit) if total > 0 else 0

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details",
)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieve document details by ID, ensuring user ownership isolation."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    doc = await db.scalar(stmt)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete document and stored file",
)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> None:
    """Delete document, cascading to related database records and cleaning up stored files."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    doc = await db.scalar(stmt)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Delete physical file from storage if present
    if doc.file_path:
        await storage.delete_file(doc.file_path)

    # Remove database record
    await db.delete(doc)
    await db.commit()

    logger.info("Deleted document id=%d for user_id=%d", document_id, current_user.id)


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry failed or pending document ingestion",
)
async def reprocess_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    embedding: EmbeddingProvider = Depends(get_embedding_provider),
) -> DocumentResponse:
    """Trigger idempotent document reprocessing, rebuilding chunks, embeddings, and summary."""
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    doc = await db.scalar(stmt)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return await ingest_document(
        document_id=doc.id,
        db=db,
        storage=storage,
        embedding_provider=embedding,
    )


@router.get(
    "/{document_id}/related",
    response_model=RelatedDocumentsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve semantically related documents by embedding similarity",
)
async def get_related_documents(
    document_id: int,
    limit: int = Query(5, ge=1, le=20, description="Maximum related documents to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RelatedDocumentsResponse:
    """Find and return similar documents within user's library by comparing centroid chunk embeddings."""
    # Verify document ownership
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    doc = await db.scalar(doc_stmt)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    related_items = await find_related_documents(
        document_id=document_id,
        user_id=current_user.id,
        db=db,
        limit=limit,
    )

    return RelatedDocumentsResponse(
        document_id=document_id,
        related=related_items,
    )
