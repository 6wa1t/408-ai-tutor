"""Repository for question assets."""

from sqlalchemy.orm import Session

from app.models.question_asset import QuestionAsset
from app.repositories.base import BaseRepository


class QuestionAssetRepository(BaseRepository[QuestionAsset]):
    """Data access layer for question assets."""

    model = QuestionAsset

    def __init__(self, db: Session):
        super().__init__(db)

    def list_for_question(self, question_id: int) -> list[QuestionAsset]:
        """Return assets for one question in stable insertion order."""
        return (
            self.db.query(QuestionAsset)
            .filter(QuestionAsset.question_id == question_id)
            .order_by(QuestionAsset.id.asc())
            .all()
        )

    def list_for_questions(
        self,
        question_ids: list[int],
    ) -> dict[int, list[QuestionAsset]]:
        """Return assets grouped by question id."""
        if not question_ids:
            return {}

        rows = (
            self.db.query(QuestionAsset)
            .filter(QuestionAsset.question_id.in_(question_ids))
            .order_by(QuestionAsset.id.asc())
            .all()
        )
        grouped: dict[int, list[QuestionAsset]] = {}
        for row in rows:
            grouped.setdefault(row.question_id, []).append(row)
        return grouped
