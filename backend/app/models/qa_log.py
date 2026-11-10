"""SQLAlchemy model for recording Q&A sessions and cited citations."""
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class QALog(Base):
    """Q&A interaction log storing questions, generated answers, and cited chunk IDs."""
    __tablename__ = "qa_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    cited_chunk_ids: Mapped[List[int]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="qa_logs")

    def __repr__(self) -> str:
        return f"<QALog id={self.id} user_id={self.user_id} q={self.question[:30]}>"
