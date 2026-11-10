"""LLM-assisted document summarization and tag generation with structured JSON validation."""
import logging
import re
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.tag import Tag
from app.services.llm import LLMProvider

logger = logging.getLogger(__name__)


class DocumentSummaryAndTags(BaseModel):
    """Pydantic schema enforcing structured JSON output from LLM for document enrichment."""
    summary: str = Field(..., description="Concise 2-3 sentence overview")
    tags: List[str] = Field(..., min_length=1, max_length=10, description="3-5 suggested lowercase tags")
    category: Optional[str] = Field(None, description="Suggested primary category")


def _extract_json_block(text: str) -> str:
    """Extract JSON string from LLM output, stripping markdown code fences if present."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


async def enrich_document_summary_and_tags(
    document: Document,
    chunks: List[Chunk],
    db: AsyncSession,
    llm: LLMProvider,
) -> None:
    """Generate summary and tags using structured LLM output (fail-soft)."""
    if not chunks:
        return

    # Take first 3 chunks as representative excerpt
    excerpt_text = "\n\n".join(c.content for c in chunks[:3])

    prompt = (
        f"Analyze the document title and content excerpt below. "
        f"Return ONLY a valid JSON object matching this schema:\n"
        f'{{"summary": "<concise 2-3 sentence summary>", "tags": ["<tag1>", "<tag2>", "<tag3>"], "category": "<category>"}}\n\n'
        f"Document Title: {document.title}\n"
        f"Excerpt:\n{excerpt_text}\n"
    )

    try:
        raw_response = await llm.generate_response(prompt)
        json_str = _extract_json_block(raw_response)
        validated = DocumentSummaryAndTags.model_validate_json(json_str)

        # Update summary
        document.summary = validated.summary.strip()

        # Update category if not already set
        if not document.category and validated.category:
            document.category = validated.category.strip().lower()

        # Add suggested tags
        for raw_tag in validated.tags:
            tag_name = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_tag.lower().strip())
            if not tag_name or len(tag_name) < 2:
                continue

            # Fetch or create Tag for user
            tag_stmt = select(Tag).where(
                Tag.user_id == document.user_id,
                Tag.name == tag_name,
            )
            tag = await db.scalar(tag_stmt)
            if not tag:
                tag = Tag(user_id=document.user_id, name=tag_name)
                db.add(tag)
                await db.flush()

            if tag not in document.tags:
                document.tags.append(tag)

        await db.commit()
        await db.refresh(document)
        logger.info(
            "Enriched document id=%d with summary and %d tags",
            document.id,
            len(validated.tags),
        )

    except Exception as exc:
        # Fail-soft: document remains ready and searchable even if summarization fails
        logger.warning(
            "Fail-soft: Document summarization failed for doc_id=%d: %s",
            document.id,
            exc,
        )
