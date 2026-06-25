"""QuestionAsset ORM model for runtime question media and text assets."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class QuestionAsset(Base):
    """Media, table, diagram, formula, or text asset linked to a question."""

    __tablename__ = "question_assets"
    __table_args__ = (
        Index("ix_question_assets_question_id", "question_id"),
        Index("ix_question_assets_asset_type", "asset_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="import"
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    question = relationship("Question")
