"""Repository for bank import records."""

from sqlalchemy.orm import Session

from app.models.bank_import import BankImport
from app.repositories.base import BaseRepository


class BankImportRepository(BaseRepository[BankImport]):
    """Data access layer for bank import records."""

    model = BankImport

    def __init__(self, db: Session):
        super().__init__(db)

    def create_record(
        self,
        bank_id: str,
        source_type: str,
        source_path: str,
        status: str = "pending",
        total_questions: int = 0,
        imported_questions: int = 0,
        qc_report_path: str | None = None,
        error_message: str | None = None,
    ) -> BankImport:
        """Create an import record and flush without committing."""
        record = BankImport(
            bank_id=bank_id,
            source_type=source_type,
            source_path=source_path,
            status=status,
            total_questions=total_questions,
            imported_questions=imported_questions,
            qc_report_path=qc_report_path,
            error_message=error_message,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_latest_for_bank(self, bank_id: str) -> BankImport | None:
        """Return the latest import record for a bank."""
        return (
            self.db.query(BankImport)
            .filter(BankImport.bank_id == bank_id)
            .order_by(
                BankImport.created_at.desc(),
                BankImport.id.desc(),
            )
            .first()
        )
