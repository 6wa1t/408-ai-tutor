"""Question Repository — specialized queries for Question model."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.question import Question
from app.repositories.base import BaseRepository


class QuestionRepository(BaseRepository[Question]):
    """Data access layer for Question model."""

    model = Question

    def __init__(self, db: Session):
        super().__init__(db)

    def get_by_subject(
        self,
        subject: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Question]:
        """Fetch questions filtered by subject."""
        return (
            self.db.query(Question)
            .filter(Question.subject == subject)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_knowledge_tag(
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Question]:
        """Search questions by knowledge tag (contains match)."""
        return (
            self.db.query(Question)
            .filter(Question.knowledge_tag.contains(tag))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_random(
        self,
        count: int = 10,
        subject: str | None = None,
        question_type: str | None = None,
    ) -> list[Question]:
        """Get random questions, optionally filtered by subject and/or question type.

        Uses SQLite's RANDOM() function. For PostgreSQL, switch to func.random().
        """
        query = self.db.query(Question)
        if subject:
            query = query.filter(Question.subject == subject)
        if question_type:
            query = query.filter(Question.question_type == question_type)
        return query.order_by(func.random()).limit(count).all()

    def get_chapters_by_subject(
        self,
        subject: str,
        question_type: str | None = None,
    ) -> list[tuple[str, int]]:
        """Get ordered chapter list for a subject with question counts.

        Returns list of (chapter_name, count) tuples, ordered by chapter name.
        """
        query = (
            self.db.query(Question.chapter, func.count(Question.id))
            .filter(Question.subject == subject)
        )
        if question_type:
            query = query.filter(Question.question_type == question_type)
        return (
            query.filter(Question.chapter.isnot(None))
            .group_by(Question.chapter)
            .order_by(Question.chapter)
            .all()
        )

    def get_by_chapter(
        self,
        subject: str,
        chapter: str,
        question_type: str | None = None,
    ) -> list[Question]:
        """Get all questions in a specific chapter, ordered by ID (original PDF order)."""
        query = (
            self.db.query(Question)
            .filter(Question.subject == subject)
            .filter(Question.chapter == chapter)
        )
        if question_type:
            query = query.filter(Question.question_type == question_type)
        return query.order_by(Question.id).all()

    def check_duplicate(self, text_hash: str) -> Question | None:
        """Check if a question with the same text hash already exists.

        Returns the existing Question or None.
        """
        return (
            self.db.query(Question)
            .filter(Question.text_hash == text_hash)
            .first()
        )

    def count_by_subject(self) -> list[tuple[str, int]]:
        """Count questions grouped by subject."""
        return (
            self.db.query(Question.subject, func.count(Question.id))
            .group_by(Question.subject)
            .all()
        )

    def search(
        self,
        subject: str | None = None,
        chapter: str | None = None,
        knowledge_tag: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Question]:
        """Multi-criteria search with pagination."""
        query = self.db.query(Question)
        if subject:
            query = query.filter(Question.subject == subject)
        if chapter:
            query = query.filter(Question.chapter == chapter)
        if knowledge_tag:
            query = query.filter(Question.knowledge_tag.contains(knowledge_tag))
        return query.offset(skip).limit(limit).all()

    def count_search(
        self,
        subject: str | None = None,
        chapter: str | None = None,
        knowledge_tag: str | None = None,
    ) -> int:
        """Count for multi-criteria search."""
        query = self.db.query(Question)
        if subject:
            query = query.filter(Question.subject == subject)
        if chapter:
            query = query.filter(Question.chapter == chapter)
        if knowledge_tag:
            query = query.filter(Question.knowledge_tag.contains(knowledge_tag))
        return query.count()
