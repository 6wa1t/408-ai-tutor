"""Repository for answer candidates."""

from sqlalchemy.orm import Session

from app.models.answer_candidate import AnswerCandidate
from app.repositories.base import BaseRepository


class AnswerCandidateRepository(BaseRepository[AnswerCandidate]):
    """Data access layer for answer candidates."""

    model = AnswerCandidate

    def __init__(self, db: Session):
        super().__init__(db)

    def create_candidate(
        self,
        question_id: int,
        source: str,
        answer_text: str,
        explanation: str | None = None,
        confidence: float | None = None,
        is_verified: bool = False,
        raw_payload: str | None = None,
    ) -> AnswerCandidate:
        """Create an answer candidate and flush without committing."""
        candidate = AnswerCandidate(
            question_id=question_id,
            source=source,
            answer_text=answer_text,
            explanation=explanation,
            confidence=confidence,
            is_verified=is_verified,
            raw_payload=raw_payload,
        )
        self.db.add(candidate)
        self.db.flush()
        return candidate

    def get_best_verified(self, question_id: int) -> AnswerCandidate | None:
        """Return the highest-confidence verified candidate for a question."""
        return (
            self.db.query(AnswerCandidate)
            .filter(AnswerCandidate.question_id == question_id)
            .filter(AnswerCandidate.is_verified.is_(True))
            .order_by(
                AnswerCandidate.confidence.desc(),
                AnswerCandidate.created_at.desc(),
                AnswerCandidate.id.desc(),
            )
            .first()
        )

    def get_latest(self, question_id: int) -> AnswerCandidate | None:
        """Return the newest candidate for a question."""
        return (
            self.db.query(AnswerCandidate)
            .filter(AnswerCandidate.question_id == question_id)
            .order_by(
                AnswerCandidate.created_at.desc(),
                AnswerCandidate.id.desc(),
            )
            .first()
        )
