"""QuizRecord ORM model — tracks user quiz attempts."""

from datetime import datetime

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class QuizRecord(Base):
    """答题记录表 — 记录每次答题的结果。"""

    __tablename__ = "quiz_records"
    __table_args__ = (
        Index("ix_quiz_records_question_id", "question_id"),
        Index("ix_quiz_records_create_time", "create_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id"), nullable=False
    )
    user_answer: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="用户提交的答案"
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否正确"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    # Relationship
    question = relationship("Question", lazy="joined")

    def __repr__(self) -> str:
        return f"<QuizRecord(id={self.id}, qid={self.question_id}, correct={self.is_correct})>"
