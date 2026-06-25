"""WeakKnowledge ORM model — tracks knowledge mastery."""

from sqlalchemy import Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class WeakKnowledge(Base):
    """薄弱知识点表 — 统计各知识点的掌握程度。"""

    __tablename__ = "weak_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    knowledge_tag: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, comment="知识点标签"
    )
    wrong_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="答错次数"
    )
    correct_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="答对次数"
    )
    mastery_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="掌握度评分 (0~1)"
    )

    subject: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chapter: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    def recalculate_mastery(self) -> None:
        """根据正确/错误次数重新计算掌握度。"""
        total = self.wrong_count + self.correct_count
        if total == 0:
            self.mastery_score = 0.0
        else:
            self.mastery_score = self.correct_count / total

    def __repr__(self) -> str:
        return f"<WeakKnowledge(tag='{self.knowledge_tag}', mastery={self.mastery_score:.2f})>"
