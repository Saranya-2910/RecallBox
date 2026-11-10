"""Business logic and external service integrations."""
from app.services.chunker import Chunker, ProcessedChunk
from app.services.embedding import (
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
    get_embedding_provider,
)
from app.services.extractor import (
    ExtractedPage,
    ExtractionError,
    extract_from_link,
    extract_from_note,
    extract_from_pdf,
)
from app.services.ingestion import ingest_document
from app.services.search import (
    ScoredChunk,
    compute_reciprocal_rank_fusion,
    deduplicate_results_by_document,
    execute_keyword_search,
    execute_semantic_search,
    search_user_chunks,
)
from app.services.storage import (
    LocalStorageService,
    StorageService,
    get_storage_service,
)

__all__ = [
    "StorageService",
    "LocalStorageService",
    "get_storage_service",
    "EmbeddingProvider",
    "MockEmbeddingProvider",
    "GeminiEmbeddingProvider",
    "SentenceTransformersEmbeddingProvider",
    "get_embedding_provider",
    "ExtractedPage",
    "ExtractionError",
    "extract_from_pdf",
    "extract_from_link",
    "extract_from_note",
    "Chunker",
    "ProcessedChunk",
    "ingest_document",
    "ScoredChunk",
    "compute_reciprocal_rank_fusion",
    "deduplicate_results_by_document",
    "execute_semantic_search",
    "execute_keyword_search",
    "search_user_chunks",
]
