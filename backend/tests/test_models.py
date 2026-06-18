"""Tests for ORM models."""

import pytest
from app.models.question import Question
from app.models.quiz_record import QuizRecord
from app.models.weak_knowledge import WeakKnowledge


class TestQuestionModel:
    """Tests for the Question model."""

    def test_create_question(self, db_session):
        """Test creating a basic question."""
        q = Question(
            subject="数据结构",
            question_type="choice",
            question_text="二叉树的中序遍历序列是什么？",
            option_a="左根右",
            option_b="根左右",
            option_c="左右根",
            option_d="右根左",
            answer="A",
            text_hash="test_hash_001",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)

        assert q.id is not None
        assert q.subject == "数据结构"
        assert q.answer == "A"

    def test_question_optional_fields(self, db_session):
        """Test that optional fields can be None."""
        q = Question(
            subject="操作系统",
            question_type="choice",
            question_text="进程和线程的区别？",
            answer="A",
            text_hash="test_hash_002",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)

        assert q.chapter is None
        assert q.option_a is None
        assert q.analysis is None
        assert q.image_path is None

    def test_question_repr(self, db_session, sample_question):
        """Test the string representation."""
        repr_str = repr(sample_question)
        assert "Question" in repr_str
        assert "数据结构" in repr_str


class TestQuizRecordModel:
    """Tests for the QuizRecord model."""

    def test_create_record(self, db_session, sample_question):
        """Test creating a quiz record."""
        record = QuizRecord(
            question_id=sample_question.id,
            user_answer="A",
            is_correct=False,
        )
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert record.id is not None
        assert record.is_correct is False
        assert record.question_id == sample_question.id


class TestWeakKnowledgeModel:
    """Tests for the WeakKnowledge model."""

    def test_recalculate_mastery(self):
        """Test mastery score calculation."""
        wk = WeakKnowledge(
            knowledge_tag="二叉树",
            wrong_count=3,
            correct_count=7,
        )
        wk.recalculate_mastery()
        assert wk.mastery_score == pytest.approx(0.7)

    def test_recalculate_mastery_zero(self):
        """Test mastery score with zero attempts."""
        wk = WeakKnowledge(
            knowledge_tag="排序",
            wrong_count=0,
            correct_count=0,
        )
        wk.recalculate_mastery()
        assert wk.mastery_score == 0.0

    def test_recalculate_mastery_perfect(self):
        """Test mastery score with all correct."""
        wk = WeakKnowledge(
            knowledge_tag="图",
            wrong_count=0,
            correct_count=10,
        )
        wk.recalculate_mastery()
        assert wk.mastery_score == pytest.approx(1.0)
