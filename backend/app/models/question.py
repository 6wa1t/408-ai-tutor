"""Question ORM model."""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Question(Base):
    """题目表 — 存储从PDF解析出的所有题目。"""

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_subject", "subject"),
        Index("ix_questions_knowledge_tag", "knowledge_tag"),
        Index("ix_questions_question_type", "question_type"),
        Index("ix_questions_text_hash", "text_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- 分类信息 ---
    subject: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="科目: 数据结构/操作系统/计算机组成原理/计算机网络"
    )
    chapter: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="章节"
    )
    knowledge_tag: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="知识点标签, 逗号分隔"
    )

    # --- 题目内容 ---
    question_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="choice", comment="题型: choice/fill/essay"
    )
    question_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="题目正文"
    )

    # --- 选项（选择题） ---
    option_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_c: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_d: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- 答案与解析 ---
    answer: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="", comment="正确答案: A/B/C/D 或文本 (题本无答案时为空)"
    )
    answer_ref: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="答案引用页码: 如'答案见原书P6'"
    )
    analysis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="解析"
    )

    # --- 附件 ---
    image_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="题目相关图片路径"
    )

    # --- 溯源 ---
    source_pdf: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="来源PDF文件名"
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="来源PDF页码(0-indexed)"
    )
    exam_year: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="统考真题年份: 如'2023统考真题'"
    )
    text_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="题目文本SHA256哈希, 用于去重"
    )

    # --- 时间戳 ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, subject='{self.subject}', text='{self.question_text[:30]}...')>"
