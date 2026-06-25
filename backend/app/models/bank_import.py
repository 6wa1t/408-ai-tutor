"""BankImport ORM model for runtime question bank import tracking."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class BankImport(Base):
    """Import run metadata for built-in or user-supplied question banks."""

    __tablename__ = "bank_imports"
    __table_args__ = (
        Index("ix_bank_imports_bank_id", "bank_id"),
        Index("ix_bank_imports_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_questions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    imported_questions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    qc_report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
