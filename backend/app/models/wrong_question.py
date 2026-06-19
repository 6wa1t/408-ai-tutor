"""WrongQuestion ORM model — 错题集。"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class WrongQuestion(Base):
    """错题记录表 — 记录用户答错的题目，支持重做和管理。"""

    __tablename__ = "wrong_questions"
    __table_args__ = (
        Index("ix_wp_subject", "subject"),
        Index("ix_wp_last_status", "last_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="关联题目ID（唯一，防止重复）",
    )

    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="auto",
        comment="来源: auto(刷题自动收集) / manual(手动添加)",
    )

    subject: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="科目（冗余字段，方便筛选）",
    )

    chapter: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="章节（冗余字段）",
    )

    last_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unreviewed",
        comment="最近重做状态: correct / wrong / unreviewed",
    )

    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="重做次数",
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="加入错题集时间",
    )

    last_review_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近一次重做时间",
    )

    # Relationship
    question = relationship("Question", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<WrongQuestion(id={self.id}, qid={self.question_id}, "
            f"status='{self.last_status}', reviews={self.review_count})>"
        )
