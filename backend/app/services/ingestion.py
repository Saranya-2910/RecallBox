"""End-to-end document ingestion pipeline: parse, chunk, embed, index, and enrich."""
import logging
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.document import DocumentStatus, SourceType
from app.services.chunker import Chunker
from app.services.embedding import EmbeddingProvider, get_embedding_provider
from app.services.extractor import (
    ExtractionError,
    extract_from_link,
    extract_from_note,
    extract_from_pdf,
)
from app.services.llm import LLMProvider, get_llm_provider
from app.services.storage import StorageService, get_storage_service
from app.services.summarizer import enrich_document_summary_and_tags

logger = logging.getLogger(__name__)


async def ingest_document(
    document_id: int,
    db: AsyncSession,
    storage: Optional[StorageService] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
    llm_provider: Optional[LLMProvider] = None,
) -> Document:
    """Execute the full ingestion pipeline for a single document.

    Lifecycle:
        pending -> processing -> ready (or failed on error).
    Idempotent:
        Deletes any pre-existing chunks for this document before creating new ones.
    Enrichment:
        Generates summary and 3-5 tags using structured LLM output (fail-soft).
    """
    if storage is None:
        storage = get_storage_service()
    if embedding_provider is None:
        embedding_provider = get_embedding_provider()
    if llm_provider is None:
        llm_provider = get_llm_provider()

    stmt = select(Document).where(Document.id == document_id)
    document = await db.scalar(stmt)
    if not document:
        raise ValueError(f"Document id={document_id} not found")

    # Step 1: Update status to processing
    document.status = DocumentStatus.PROCESSING.value
    document.error = None
    await db.commit()
    await db.refresh(document)

    try:
        # Step 2: Extract text based on source type
        pages = []
        if document.source_type == SourceType.PDF.value:
            if not document.file_path:
                raise ExtractionError("PDF document missing stored file path")
            pages = extract_from_pdf(document.file_path)

        elif document.source_type == SourceType.LINK.value:
            if not document.source_url:
                raise ExtractionError("Link document missing source URL")
            pages = await extract_from_link(document.source_url)

        elif document.source_type == SourceType.NOTE.value:
            if document.file_path:
                raw_bytes = await storage.read_file(document.file_path)
                pages = extract_from_note(raw_bytes.decode("utf-8"))
            else:
                pages = extract_from_note(document.title)

        else:
            raise ExtractionError(f"Unsupported source type: {document.source_type}")

        # Step 3: Chunk text into 500-800 token passages with overlap
        chunker = Chunker()
        processed_chunks = chunker.chunk_pages(pages)

        if not processed_chunks:
            raise ExtractionError("No extractable text chunks could be produced")

        # Step 4: Batch generate vector embeddings
        chunk_texts = [c.content for c in processed_chunks]
        embeddings = await embedding_provider.embed_texts(chunk_texts)

        # Step 5: Idempotently delete old chunks if reprocessing
        await db.execute(delete(Chunk).where(Chunk.document_id == document.id))

        # Step 6: Insert new chunk records
        is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False

        created_chunks: List[Chunk] = []
        for pc, emb in zip(processed_chunks, embeddings):
            chunk = Chunk(
                document_id=document.id,
                user_id=document.user_id,
                chunk_index=pc.chunk_index,
                content=pc.content,
                page_number=pc.page_number,
                embedding=emb,
                tsv=func.to_tsvector("english", pc.content) if is_postgres else None,
            )
            db.add(chunk)
            created_chunks.append(chunk)

        # Step 7: Mark document ready
        document.status = DocumentStatus.READY.value
        document.error = None
        await db.commit()
        await db.refresh(document)

        # Step 8: Auto-enrich summary and suggested tags (fail-soft)
        await enrich_document_summary_and_tags(document, created_chunks, db, llm_provider)

        logger.info(
            "Document id=%d ingestion completed successfully with %d chunks",
            document.id,
            len(processed_chunks),
        )
        return document

    except Exception as exc:
        logger.error(
            "Ingestion pipeline failed for document id=%d: %s",
            document.id,
            exc,
            exc_info=True,
        )
        document.status = DocumentStatus.FAILED.value
        document.error = str(exc)
        await db.commit()
        await db.refresh(document)
        return document
