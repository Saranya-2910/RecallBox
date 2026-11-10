"""Tag management endpoints: list tags, and add/remove tags on documents."""
import logging
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.tag import Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tags"])


@router.get(
    "/tags",
    response_model=List[TagResponse],
    status_code=status.HTTP_200_OK,
    summary="List all tags for the current user",
)
async def list_user_tags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TagResponse]:
    """Retrieve all distinct tags created by or suggested for the authenticated user."""
    stmt = (
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .order_by(Tag.name.asc())
    )
    result = await db.scalars(stmt)
    return list(result.all())


@router.post(
    "/documents/{document_id}/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a tag to a document",
)
async def add_document_tag(
    document_id: int,
    payload: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """Manually link a tag to a user's document, creating the tag if non-existent."""
    # Verify document ownership
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    document = await db.scalar(doc_stmt)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "", payload.name.lower().strip())
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag name must contain alphanumeric characters",
        )

    # Fetch or create Tag for user
    tag_stmt = select(Tag).where(
        Tag.user_id == current_user.id,
        Tag.name == clean_name,
    )
    tag = await db.scalar(tag_stmt)
    if not tag:
        tag = Tag(user_id=current_user.id, name=clean_name)
        db.add(tag)
        await db.flush()

    if tag not in document.tags:
        document.tags.append(tag)
        await db.commit()
        await db.refresh(document)

    return tag


@router.delete(
    "/documents/{document_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a tag from a document",
)
async def remove_document_tag(
    document_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unlink a tag from a document."""
    doc_stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id,
    )
    document = await db.scalar(doc_stmt)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    tag_stmt = select(Tag).where(
        Tag.id == tag_id,
        Tag.user_id == current_user.id,
    )
    tag = await db.scalar(tag_stmt)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )

    if tag in document.tags:
        document.tags.remove(tag)
        await db.commit()
