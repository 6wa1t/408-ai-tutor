"""Quiz Repository — data access for quiz records and statistics."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.quiz_record import QuizRecord
from app.models.weak_knowledge import WeakKnowledge
from app.repositories.base import BaseRepository


class QuizRepository(BaseRepository[QuizRecord]):
    """Data access layer for QuizRecord model."""

    model = QuizRecord

    def __init__(self, db: Session):
        super().__init__(db)

    def create_record(
        self,
        question_id: int,
        user_answer: str,
        is_correct: bool,
    ) -> QuizRecord:
        """Create a new quiz attempt record."""
        record = QuizRecord(
            question_id=question_id,
            user_answer=user_answer,
            is_correct=is_correct,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_history(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[QuizRecord]:
        """Get recent quiz history with question details."""
        return (
            self.db.query(QuizRecord)
            .order_by(QuizRecord.create_time.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_total_stats(self) -> tuple[int, int]:
        """Return (total_attempts, total_correct)."""
        from sqlalchemy import text
        row = self.db.execute(text(
            "SELECT COUNT(*), SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) FROM quiz_records"
        )).fetchone()
        total = row[0] or 0
        correct = int(row[1] or 0)
        return total, correct

    def get_subject_stats(self) -> list[dict]:
        """Get accuracy statistics grouped by subject."""
        from sqlalchemy import text
        rows = self.db.execute(text("""
            SELECT q.subject,
                   COUNT(*) as total,
                   SUM(CASE WHEN qr.is_correct THEN 1 ELSE 0 END) as correct
            FROM quiz_records qr
            JOIN questions q ON qr.question_id = q.id
            GROUP BY q.subject
        """)).fetchall()

        return [
            {"subject": row[0], "total": row[1], "correct": row[2], "accuracy": row[2] / row[1] if row[1] else 0}
            for row in rows
        ]


class WeakKnowledgeRepository(BaseRepository[WeakKnowledge]):
    """Data access layer for WeakKnowledge model."""

    model = WeakKnowledge

    def __init__(self, db: Session):
        super().__init__(db)

    def get_by_tag(self, tag: str) -> WeakKnowledge | None:
        """Find a weak knowledge entry by exact tag match."""
        return (
            self.db.query(WeakKnowledge)
            .filter(WeakKnowledge.knowledge_tag == tag)
            .first()
        )

    def get_weakest(self, limit: int = 10) -> list[WeakKnowledge]:
        """Get the weakest knowledge points (lowest mastery score)."""
        return (
            self.db.query(WeakKnowledge)
            .filter(WeakKnowledge.wrong_count > 0)
            .order_by(WeakKnowledge.mastery_score.asc())
            .limit(limit)
            .all()
        )

    def update_stats(
        self,
        tag: str,
        is_correct: bool,
    ) -> WeakKnowledge:
        """Update or create weak knowledge stats for a tag.

        Args:
            tag: Knowledge tag string.
            is_correct: Whether the user answered correctly.

        Returns:
            The updated WeakKnowledge record.
        """
        wk = self.get_by_tag(tag)
        if wk is None:
            wk = WeakKnowledge(
                knowledge_tag=tag,
                wrong_count=0,
                correct_count=0,
                mastery_score=0.0,
            )
            self.db.add(wk)

        if is_correct:
            wk.correct_count += 1
        else:
            wk.wrong_count += 1

        wk.recalculate_mastery()
        self.db.flush()
        return wk
