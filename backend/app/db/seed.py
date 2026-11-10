"""Database seeding script for RecallBox.

Creates a demo user (demo@recallbox.dev) and seeds realistic sample documents,
chunks, vector embeddings, and tags for rapid evaluation and local demonstration.
"""
import asyncio
import hashlib
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path if invoked directly
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import get_password_hash  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.tag import Tag  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.embedding import get_embedding_provider  # noqa: E402

logger = logging.getLogger(__name__)

DEMO_USER_EMAIL = "demo@recallbox.dev"
DEMO_USER_PASSWORD = "RecallBox2026!"

SAMPLE_DOCUMENTS = [
    {
        "title": "FastAPI Dependency Injection and Lifespan Architecture",
        "source_type": "pdf",
        "category": "Architecture",
        "tags": ["fastapi", "backend", "python", "async"],
        "summary": "Comprehensive overview of FastAPI dependency graphs, yield dependencies for database sessions, and asynccontextmanager lifespan orchestration.",
        "pages": [
            {
                "page": 1,
                "text": "FastAPI features a declarative Dependency Injection system utilizing Depends. When route handlers declare dependencies, FastAPI resolves sub-dependencies hierarchically before invoking the endpoint. This allows clean abstraction for database sessions, authentication, and rate limiting.",
            },
            {
                "page": 2,
                "text": "Database sessions are safely managed via yield dependencies. The dependency establishes an asynchronous database session, yields to the request handler, and guarantees commit, rollback, and connection cleanup in the finally block even when exceptions occur.",
            },
            {
                "page": 3,
                "text": "Application lifespan context managers replace legacy startup and shutdown event decorators. Using @asynccontextmanager, applications initialize connection pools and machine learning models prior to serving traffic, followed by clean worker teardown.",
            },
        ],
    },
    {
        "title": "PostgreSQL pgvector: HNSW Graph Indexing vs IVFFlat",
        "source_type": "pdf",
        "category": "Database",
        "tags": ["pgvector", "postgres", "vector-search", "hnsw"],
        "summary": "Detailed comparison of pgvector indexing strategies, comparing multi-layer HNSW graph exploration against k-means IVFFlat clustering.",
        "pages": [
            {
                "page": 1,
                "text": "pgvector adds vector similarity search to PostgreSQL via cosine distance (<=>), Euclidean distance (<->), and inner product (<#>). Indexing high-dimensional embeddings is required to avoid linear sequential table scans.",
            },
            {
                "page": 2,
                "text": "HNSW (Hierarchical Navigable Small World) constructs a multi-layer graph index. Parameter m specifies connections per node and ef_construction sets index build depth. HNSW offers superior recall and queries per second without requiring pre-clustering training.",
            },
            {
                "page": 3,
                "text": "IVFFlat partitions vectors into Voronoi cells using k-means clustering. It requires existing table data before index creation to compute representative centroids; indexing empty tables produces suboptimal retrieval accuracy.",
            },
        ],
    },
    {
        "title": "Reciprocal Rank Fusion Hybrid Search Strategy",
        "source_type": "link",
        "category": "Search",
        "tags": ["search", "rrf", "hybrid-search", "bm25"],
        "summary": "Analysis of Cormack Reciprocal Rank Fusion for combining lexical keyword rankings with dense semantic vector rankings without score calibration.",
        "pages": [
            {
                "page": 1,
                "text": "Lexical keyword search using Postgres tsvector and dense semantic vector search with pgvector have non-comparable score distributions. Direct score addition creates skew and requires brittle manual calibration.",
            },
            {
                "page": 2,
                "text": "Reciprocal Rank Fusion (RRF) merges search rankings based strictly on positional rank: RRF_score = SUM( 1.0 / (60 + rank_i) ). RRF ensures documents favored by both search systems rise to the top while preventing single-algorithm outlier scores from skewing results.",
            },
        ],
    },
    {
        "title": "RAG Hallucination Mitigation & Two-Pass Citation Auditing",
        "source_type": "note",
        "category": "AI/RAG",
        "tags": ["rag", "citations", "grounding", "llm"],
        "summary": "Engineering reliable RAG systems through strict system grounding prompts, explicit refusal thresholds, and post-generation citation validation against retrieved chunk IDs.",
        "pages": [
            {
                "page": 1,
                "text": "Generative language models hallucinate when questions cannot be answered from retrieved context. A strict grounding system prompt enforces explicit refusals ('This information is not found in your saved material') whenever evidence is absent.",
            },
            {
                "page": 2,
                "text": "To guarantee auditability, generated answers cite chunk IDs. A validation layer verifies that every cited chunk ID was present in the retrieved candidate set, discarding hallucinated references before persisting the Q&A log.",
            },
        ],
    },
]


async def seed_database(db: AsyncSession) -> None:
    """Seed the database with the default demo user and indexed sample documents."""
    # 1. Seed or retrieve Demo User
    user_stmt = select(User).where(User.email == DEMO_USER_EMAIL)
    demo_user = await db.scalar(user_stmt)

    if not demo_user:
        hashed = get_password_hash(DEMO_USER_PASSWORD)
        demo_user = User(
            email=DEMO_USER_EMAIL,
            password_hash=hashed,
        )
        db.add(demo_user)
        await db.flush()
        await db.refresh(demo_user)
        print(f"[Seed] Created demo user: {DEMO_USER_EMAIL} (password: {DEMO_USER_PASSWORD})")
    else:
        print(f"[Seed] Demo user already exists: {DEMO_USER_EMAIL}")

    embedding_provider = get_embedding_provider()

    # 2. Seed Documents
    for item in SAMPLE_DOCUMENTS:
        title = item["title"]
        content_hash = hashlib.sha256(title.encode("utf-8")).hexdigest()

        # Check existing
        doc_stmt = select(Document).where(
            Document.user_id == demo_user.id,
            Document.title == title,
        )
        doc = await db.scalar(doc_stmt)

        if not doc:
            doc = Document(
                user_id=demo_user.id,
                title=title,
                source_type=item["source_type"],
                category=item["category"],
                summary=item.get("summary"),
                status="ready",
                content_hash=content_hash,
            )
            db.add(doc)
            await db.flush()
            await db.refresh(doc)
            print(f"[Seed] Created document: '{title}' (ID: {doc.id})")

            # Seed Chunks
            for idx, p in enumerate(item["pages"]):
                content = p["text"]
                emb = await embedding_provider.embed_query(content)
                chunk = Chunk(
                    document_id=doc.id,
                    user_id=demo_user.id,
                    chunk_index=idx,
                    content=content,
                    page_number=p.get("page", idx + 1),
                    embedding=emb,
                )
                db.add(chunk)

            # Seed Tags
            for tag_name in item.get("tags", []):
                clean_tag = tag_name.strip().lower()
                tag_stmt = select(Tag).where(
                    Tag.user_id == demo_user.id,
                    Tag.name == clean_tag,
                )
                tag = await db.scalar(tag_stmt)
                if not tag:
                    tag = Tag(user_id=demo_user.id, name=clean_tag)
                    db.add(tag)
                    await db.flush()
                    await db.refresh(tag)

                if tag not in doc.tags:
                    doc.tags.append(tag)

            await db.commit()
        else:
            print(f"[Seed] Document already exists: '{title}' (ID: {doc.id})")

    print("[Seed] Database seeding completed successfully!")


async def main():
    async with async_session_factory() as db:
        await seed_database(db)


if __name__ == "__main__":
    asyncio.run(main())
