# RecallBox

Personal Knowledge Base with Semantic Search and Cited Q&A (RAG).

RecallBox allows users to ingest PDFs, links, and notes, indexing them into vector and full-text searchable chunks. Users can search their library via semantic, keyword, or hybrid (Reciprocal Rank Fusion) search, and ask questions to receive answers grounded strictly in their saved materials with page-level citations.

---

## Tech Stack

- **Backend API:** FastAPI (Python 3.11/3.12), Pydantic v2, `pydantic-settings`
- **Database:** PostgreSQL 16 with `pgvector`
- **ORM & Migrations:** SQLAlchemy 2.x (Asyncio), Alembic
- **Background Jobs:** Celery + Redis
- **Auth:** JWT (access token) + bcrypt/argon2 hashing (scoped per user)
- **Embeddings & LLM:** Wrapped behind abstract provider interfaces (Gemini API / Sentence-Transformers)
- **Frontend:** React + Vite + Tailwind CSS
- **Testing & CI:** Pytest, HTTPX, GitHub Actions

---

## Repository Structure

```
recallbox/
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions pipeline (linting, migrations, pytest)
├── backend/
│   ├── alembic/
│   │   ├── versions/              # Database migration scripts
│   │   │   └── 0001_enable_pgvector.py
│   │   └── env.py                 # Async Alembic runner
│   ├── app/
│   │   ├── api/                   # API routes (health, auth, documents, search, ask)
│   │   ├── core/                  # Settings, logging, security
│   │   ├── db/                    # Async engine, session, DeclarativeBase
│   │   ├── models/                # SQLAlchemy models (users, documents, chunks, tags)
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   ├── services/              # Business logic (storage, parser, chunker, LLM)
│   │   ├── workers/               # Celery worker definitions
│   │   └── main.py                # FastAPI entrypoint, middleware, lifespan
│   ├── tests/
│   │   ├── conftest.py            # Test fixtures and async client setup
│   │   └── test_health.py         # Health and connectivity tests
│   ├── Dockerfile
│   ├── pyproject.toml             # Ruff & pytest configuration
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   └── pages/
│   ├── Dockerfile
│   ├── index.html
│   └── package.json
├── eval/
│   ├── questions.json             # Retrieval evaluation benchmark set
│   └── run_eval.py                # Evaluation runner script
├── .env.example                   # Environment configuration template
├── docker-compose.yml             # Single-command orchestration
└── README.md
```

---

## Quickstart

### 1. Run with Docker Compose

Start the entire stack (PostgreSQL + pgvector, Redis, API, Celery worker, Frontend):

```bash
cp .env.example .env
docker-compose up --build
```

- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
- Frontend: [http://localhost:3000](http://localhost:3000)

### 2. Local Development (without Docker)

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Run migrations
cd backend
alembic upgrade head

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running Tests & Linting

```bash
cd backend

# Run Ruff linter
ruff check .

# Run Pytest suite
pytest -v
```

---

## Decisions

### 1. Dialect-Agnostic Alembic Migrations
- **Context:** The production and CI environments run PostgreSQL 16 with `pgvector/pgvector:pg16`, while local and lightweight integration tests can optionally run with in-memory SQLite for rapid verification without spinning up heavy external services.
- **Decision:** The initial migration (`0001_enable_pgvector.py`) inspects `op.get_bind().dialect.name`. `CREATE EXTENSION IF NOT EXISTS vector;` executes only when the target dialect is PostgreSQL.
- **Interview Takeaway:** Prevents schema migrations from breaking during rapid SQLite test runs while ensuring the extension is deterministically provisioned in PostgreSQL environments.

### 2. Async SQLAlchemy 2.0 with Session Scoping
- **Context:** High-concurrency I/O bound endpoints (search, upload status polling, ask) require non-blocking database connections.
- **Decision:** Used SQLAlchemy 2.0 `async_sessionmaker` and `AsyncSession` with `pool_pre_ping=True` and structured `get_db` dependency injection with automatic transaction commits and rollbacks on failure.
- **Interview Takeaway:** Async SQLAlchemy 2.0 prevents blocking the event loop on database queries, scaling I/O throughput under heavy concurrent load.

### 3. Pydantic-Settings with Dynamic CORS Parsing
- **Context:** Environment variables for CORS origins may be passed as JSON lists (`["http://localhost:3000"]`) or comma-separated strings.
- **Decision:** Implemented a `@field_validator` on `CORS_ORIGINS` in `Settings` that automatically parses both JSON arrays and comma-separated string inputs into `List[str]`.
- **Interview Takeaway:** Bulletproof configuration parsing prevents deployment configuration bugs across various cloud platforms (Docker, Render, Vercel).

### 4. Direct Bcrypt Hashing over Deprecated Passlib
- **Context:** The historical standard library `passlib` is unmaintained and introduces runtime deprecation/version inspection breakages on Python 3.12 with modern `bcrypt` releases.
- **Decision:** Implemented password hashing and verification using `bcrypt` directly with `gensalt()` and UTF-8 encoding.
- **Interview Takeaway:** Modern, zero-legacy dependency setup with zero deprecation warnings, retaining standard bcrypt work factor security.

### 5. Resilient Sliding-Window Login Rate Limiting
- **Context:** Authentication endpoints must be protected against credential stuffing and brute force attempts, but should not crash if an external cache is temporarily unreachable during startup or unit testing.
- **Decision:** Built a sliding-window rate limiter with an in-memory fallback tracking timestamped attempts per `IP:email` tuple, rejecting requests beyond 5 attempts per 60 seconds with HTTP 429.
- **Interview Takeaway:** Provides multi-layered defense against brute force attacks with graceful degradation.

### 6. Strict User Isolation via Injected Dependency
- **Context:** Multi-tenant security requires that no user can read or mutate another user's documents, chunks, or queries.
- **Decision:** Every protected route injects `get_current_user`, which validates the cryptographic JWT signature, checks expiration, and retrieves the verified `User` record.
- **Interview Takeaway:** Eliminates client-provided `user_id` query parameters; the user identity is derived strictly from the verified JWT payload.

### 7. StorageService Interface & Directory-Isolated Local Backend
- **Context:** Intake requires storing raw PDF files and notes on disk, but cloud production deployments will migrate to S3/GCS.
- **Decision:** Built an abstract `StorageService` interface (`save_file`, `read_file`, `delete_file`) implemented by `LocalStorageService`. Stored files are structured under `{base_dir}/{user_id}/{uuid}_{sanitized_name}` with strict path traversal checking.
- **Interview Takeaway:** Decouples file handling from HTTP handlers, enabling cloud storage migration with zero changes to business logic while enforcing filesystem-level user isolation.

### 8. Multi-Layer File Integrity & Magic Byte Validation
- **Context:** Malicious or malformed files can compromise downstream text extraction workers if only extension or client-reported MIME type is inspected.
- **Decision:** Validations enforce `.pdf` file extension, `application/pdf` MIME type, a maximum size cap (`MAX_UPLOAD_SIZE_MB`), and binary magic bytes checking (`%PDF-` header).
- **Interview Takeaway:** Defense-in-depth file validation blocks renamed executables or corrupted binaries before storage or Celery processing.

### 9. Per-User Content Hash Deduplication
- **Context:** Repeated uploads of the same article or book waste storage, worker compute, and vector database capacity.
- **Decision:** Generated SHA-256 checksums (`content_hash`) indexed and scoped to `user_id`. Duplicate attempts trigger HTTP 409 Conflict.
- **Interview Takeaway:** Prevents duplicate chunking and embedding costs while preserving user privacy across tenants.

### 10. Abstract EmbeddingProvider Strategy Pattern
- **Context:** Tests and local development cannot depend on live third-party API keys or internet availability, but production requires state-of-the-art embedding models.
- **Decision:** Placed embeddings behind an abstract `EmbeddingProvider` interface implemented by `GeminiEmbeddingProvider` (with exponential backoff and batching), `SentenceTransformersEmbeddingProvider`, and `MockEmbeddingProvider` (deterministic normalized vectors from SHA-256).
- **Interview Takeaway:** Enables 100% offline unit and integration testing with zero external dependencies, making the test suite lightning fast, hermetic, and free.

### 11. Boundary-Aware Semantic Chunking with 15% Overlap
- **Context:** Naive fixed-size character chunking splits sentences and code blocks down the middle, degrading vector retrieval and citation accuracy.
- **Decision:** The `Chunker` splits on paragraph boundaries (`\n\n`) first and falls back to sentence boundaries for long paragraphs, enforcing a 500-800 token budget with ~15% token carryover into consecutive chunks.
- **Interview Takeaway:** Preserves semantic cohesion and context continuity across chunk boundaries, directly boosting downstream retrieval recall (Hit@K).

### 12. Idempotent Ingestion Pipeline and Fail-Soft Worker
- **Context:** Retrying ingestion on failed documents or worker restarts can create orphaned or duplicate chunk rows.
- **Decision:** Reprocessing atomically prunes existing chunks in the same database transaction before indexing new ones. Corrupted or unreadable files update `status=failed` with readable errors without terminating the background worker.
- **Interview Takeaway:** Ensures fault tolerance and self-healing in distributed worker architectures.
