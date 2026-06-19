"""WrongQuestion Repository — data access for wrong question records."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.wrong_question import WrongQuestion
from app.repositories.base import BaseRepository


class WrongQuestionRepository(BaseRepository[WrongQuestion]):
    """Data access layer for WrongQuestion model."""

    model = WrongQuestion

    def __init__(self, db: Session):
        super().__init__(db)

    def add_or_update(
        self,
        question_id: int,
        subject: str,
        chapter: str | None,
        source: str = "auto",
    ) -> WrongQuestion:
        """Upsert: insert new or update existing wrong question.

        If question_id already exists, updates last_status to 'wrong'.
        Returns the WrongQuestion row.
        """
        existing = (
            self.db.query(WrongQuestion)
            .filter(WrongQuestion.question_id == question_id)
            .first()
        )
        if existing:
            existing.last_status = "wrong"
            existing.subject = subject
            existing.chapter = chapter
            self.db.flush()
            return existing

        wq = WrongQuestion(
            question_id=question_id,
            source=source,
            subject=subject,
            chapter=chapter or "",
            last_status="unreviewed",
            review_count=0,
        )
        self.db.add(wq)
        self.db.flush()
        return wq

    def remove(self, wrong_id: int) -> bool:
        """Delete by wrong_questions.id. Returns True if deleted."""
        return self.delete(wrong_id)

    def remove_by_question_id(self, question_id: int) -> bool:
        """Delete by question_id FK."""
        wq = (
            self.db.query(WrongQuestion)
            .filter(WrongQuestion.question_id == question_id)
            .first()
        )
        if wq:
            self.db.delete(wq)
            self.db.flush()
            return True
        return False

    def batch_remove(self, wrong_ids: list[int]) -> int:
        """Delete multiple wrong questions. Returns count deleted."""
        count = 0
        for wid in wrong_ids:
            if self.delete(wid):
                count += 1
        return count

    def get_with_question(self, wrong_id: int) -> WrongQuestion | None:
        """Get single row with eagerly loaded question."""
        return (
            self.db.query(WrongQuestion)
            .options(joinedload(WrongQuestion.question))
            .filter(WrongQuestion.id == wrong_id)
            .first()
        )

    def list_filtered(
        self,
        subject: str | None = None,
        chapter: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[WrongQuestion]:
        """Paginated, filtered list with eager-loaded question."""
        q = self.db.query(WrongQuestion).options(
            joinedload(WrongQuestion.question)
        )
        if subject:
            q = q.filter(WrongQuestion.subject == subject)
        if chapter:
            q = q.filter(WrongQuestion.chapter == chapter)
        if status and status != "all":
            q = q.filter(WrongQuestion.last_status == status)
        return (
            q.order_by(WrongQuestion.added_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_filtered(
        self,
        subject: str | None = None,
        chapter: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count matching rows."""
        q = self.db.query(WrongQuestion)
        if subject:
            q = q.filter(WrongQuestion.subject == subject)
        if chapter:
            q = q.filter(WrongQuestion.chapter == chapter)
        if status and status != "all":
            q = q.filter(WrongQuestion.last_status == status)
        return q.count()

    def update_review(self, wrong_id: int, is_correct: bool) -> WrongQuestion | None:
        """Update review status after a re-challenge attempt."""
        wq = self.get_by_id(wrong_id)
        if not wq:
            return None
        wq.last_status = "correct" if is_correct else "wrong"
        wq.review_count += 1
        wq.last_review_at = datetime.now()
        self.db.flush()
        return wq

    def get_stats(self) -> dict:
        """Aggregate stats: total, by_subject, by_status."""
        total = self.count()

        # By subject
        subject_rows = (
            self.db.query(WrongQuestion.subject, func.count(WrongQuestion.id))
            .group_by(WrongQuestion.subject)
            .all()
        )
        by_subject = {row[0]: row[1] for row in subject_rows}

        # By status
        status_rows = (
            self.db.query(WrongQuestion.last_status, func.count(WrongQuestion.id))
            .group_by(WrongQuestion.last_status)
            .all()
        )
        by_status = {row[0]: row[1] for row in status_rows}

        # Review rate
        reviewed = by_status.get("correct", 0) + by_status.get("wrong", 0)
        review_rate = reviewed / total if total > 0 else 0.0

        return {
            "total": total,
            "by_subject": by_subject,
            "by_status": by_status,
            "review_rate": round(review_rate, 2),
        }

    def get_chapters_for_subject(self, subject: str) -> list[str]:
        """Distinct chapters within a subject."""
        rows = (
            self.db.query(WrongQuestion.chapter)
            .filter(WrongQuestion.subject == subject)
            .filter(WrongQuestion.chapter.isnot(None))
            .filter(WrongQuestion.chapter != "")
            .distinct()
            .order_by(WrongQuestion.chapter)
            .all()
        )
        return [row[0] for row in rows]

    def get_by_question_id(self, question_id: int) -> WrongQuestion | None:
        """Find by question_id FK."""
        return (
            self.db.query(WrongQuestion)
            .filter(WrongQuestion.question_id == question_id)
            .first()
        )
