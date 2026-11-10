"""SQLAlchemy models for tags and many-to-many document tagging."""
from typing import TYPE_CHECKING, List

from sqlalchemy import Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User

# Many-to-many association table linking documents and tags
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """Tag entity for categorizing and organizing documents per user."""
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_tag_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tags")
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        secondary=document_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name={self.name} user_id={self.user_id}>"
