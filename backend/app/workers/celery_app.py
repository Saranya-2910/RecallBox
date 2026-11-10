"""Celery application configuration and worker tasks."""
import asyncio
import logging

from celery import Celery

from app.core.config import settings
from app.db.session import async_session_factory
from app.services.ingestion import ingest_document

logger = logging.getLogger(__name__)

celery_app = Celery(
    "recallbox_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="ping")
def ping_task() -> str:
    """Worker placeholder ping task."""
    return "pong"


@celery_app.task(name="process_document", bind=True, max_retries=1)
def process_document_task(self, document_id: int) -> dict:
    """Background task to parse, chunk, embed, and index a document."""
    logger.info("Celery task started for document_id=%d", document_id)

    async def _run() -> dict:
        async with async_session_factory() as session:
            doc = await ingest_document(document_id=document_id, db=session)
            return {
                "document_id": doc.id,
                "status": doc.status,
                "error": doc.error,
            }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_run(), loop)
            return future.result()
        else:
            return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Error executing process_document task for doc_id=%d: %s", document_id, exc)
        return {"document_id": document_id, "status": "failed", "error": str(exc)}
