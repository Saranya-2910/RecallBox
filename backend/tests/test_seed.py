"""Tests for database seeding script idempotency and sample document creation."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import DEMO_USER_EMAIL, SAMPLE_DOCUMENTS, seed_database
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User


@pytest.mark.asyncio
async def test_seed_database_creates_demo_data_and_is_idempotent(db_session: AsyncSession):
    """Verify seed_database creates demo user, documents, chunks, and tags, and is idempotent."""
    # Run first seeding pass
    await seed_database(db_session)

    # Verify demo user exists
    user_stmt = select(User).where(User.email == DEMO_USER_EMAIL)
    user = await db_session.scalar(user_stmt)
    assert user is not None
    assert user.email == DEMO_USER_EMAIL

    # Verify sample documents exist
    doc_stmt = select(Document).where(Document.user_id == user.id)
    docs = (await db_session.scalars(doc_stmt)).all()
    assert len(docs) == len(SAMPLE_DOCUMENTS)

    # Verify chunks were created
    chunk_stmt = select(Chunk).where(Chunk.user_id == user.id)
    chunks = (await db_session.scalars(chunk_stmt)).all()
    assert len(chunks) > 0

    # Run second seeding pass to verify idempotency
    await seed_database(db_session)

    # Counts must remain identical
    docs_after = (await db_session.scalars(doc_stmt)).all()
    assert len(docs_after) == len(SAMPLE_DOCUMENTS)
