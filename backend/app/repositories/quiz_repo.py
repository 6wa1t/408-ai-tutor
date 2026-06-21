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

    def get_all_filtered(
        self,
        subject: str | None = None,
        limit: int = 50,
        min_wrong: int = 0,
    ) -> list[dict]:
        """Query weak knowledge entries with optional filters.

        Returns list of dicts including subject derived from linked questions.
        """
        from app.models.question import Question

        query = self.db.query(WeakKnowledge)

        if min_wrong > 0:
            query = query.filter(WeakKnowledge.wrong_count >= min_wrong)

        entries = query.order_by(WeakKnowledge.mastery_score.asc()).limit(limit).all()

        results = []
        for wk in entries:
            subj = None
            if subject:
                subj = subject
            else:
                # Derive subject from the most recent question with this tag
                q = (
                    self.db.query(Question.subject)
                    .filter(Question.knowledge_tag.contains(wk.knowledge_tag))
                    .first()
                )
                subj = q.subject if q else None
            results.append({
                "knowledge_tag": wk.knowledge_tag,
                "wrong_count": wk.wrong_count,
                "correct_count": wk.correct_count,
                "mastery_score": wk.mastery_score,
                "subject": subj,
            })

        if subject:
            results = [r for r in results if r["subject"] == subject]

        return results

    def get_summary(self) -> dict:
        """Get aggregated weak knowledge summary.

        Returns total weak points, average mastery, and weakest 5 per subject.
        """
        from app.models.question import Question

        entries = self.db.query(WeakKnowledge).filter(
            WeakKnowledge.wrong_count > 0
        ).all()

        total = len(entries)
        avg_mastery = (
            sum(e.mastery_score for e in entries) / total if total > 0 else 0.0
        )

        # Group by subject via question join
        subject_map: dict[str, list[dict]] = {}
        for wk in entries:
            q = (
                self.db.query(Question.subject)
                .filter(Question.knowledge_tag.contains(wk.knowledge_tag))
                .first()
            )
            subj = q.subject if q else "未知"
            subject_map.setdefault(subj, []).append({
                "knowledge_tag": wk.knowledge_tag,
                "wrong_count": wk.wrong_count,
                "mastery_score": wk.mastery_score,
            })

        weakest_by_subject = {
            subj: sorted(items, key=lambda x: x["mastery_score"])[:5]
            for subj, items in subject_map.items()
        }

        return {
            "total_weak_points": total,
            "average_mastery": round(avg_mastery, 4),
            "weakest_by_subject": weakest_by_subject,
        }
