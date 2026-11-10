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
