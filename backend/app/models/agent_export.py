"""Agent export ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AgentExport(Base):
    """Tracks generated Agent note export runs."""

    __tablename__ = "agent_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_root: Mapped[str] = mapped_column(String(500), nullable=False)
    manifest_path: Mapped[str] = mapped_column(String(500), nullable=False)
    json_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    markdown_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    weak_point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    misconception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
