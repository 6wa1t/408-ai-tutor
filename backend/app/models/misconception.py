"""Misconception ORM model — 错题误区知识库。"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Misconception(Base):
    """误区记录表 — 记录每次答错后的AI分析结果。

    flowus_synced 用于增量同步：cron 定时任务只推送 flowus_synced=0 的记录，
    推送成功后标记为 1，避免重复推送。
    """

    __tablename__ = "misconceptions"
    __table_args__ = (
        Index("ix_misconceptions_subject", "subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id"), nullable=False, comment="关联题目ID"
    )
    subject: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="科目"
    )
    chapter: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="章节"
    )
    user_answer: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="用户的错误答案"
    )
    correct_answer: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="正确答案"
    )

    # AI-generated analysis
    misconception_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="误区概述: 用户为什么选错, 错误思维是什么"
    )
    knowledge_gap: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="知识盲区: 需要补强的核心知识点"
    )
    remediation: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="纠正建议: 如何避免再犯"
    )

    # Tracking
    frequency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="同类错误出现次数"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    flowus_synced: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="FlowUs同步状态: 0=未同步, 1=已同步 (cron增量推送用)"
    )

    def __repr__(self) -> str:
        return (
            f"<Misconception(id={self.id}, subject='{self.subject}', "
            f"Q#{self.question_id})>"
        )
