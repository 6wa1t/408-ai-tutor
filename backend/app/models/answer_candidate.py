"""AnswerCandidate ORM model for generated or extracted answer candidates."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class AnswerCandidate(Base):
    """Candidate answer with provenance, confidence, and verification state."""

    __tablename__ = "answer_candidates"
    __table_args__ = (
        Index("ix_answer_candidates_question_id", "question_id"),
        Index("ix_answer_candidates_source", "source"),
        Index("ix_answer_candidates_is_verified", "is_verified"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    question = relationship("Question")
