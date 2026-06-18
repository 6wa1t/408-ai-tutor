"""Tests for quiz service business logic."""

import pytest

from app.models.question import Question
from app.services.quiz_service import QuizService
from app.core.exceptions import QuestionNotFoundError


class TestQuizService:
    """Tests for QuizService."""

    def _create_questions(self, db_session, count=5):
        """Helper to create multiple test questions."""
        questions = []
        for i in range(count):
            q = Question(
                subject="数据结构",
                question_text=f"测试题目第{i+1}题",
                option_a="A选项",
                option_b="B选项",
                option_c="C选项",
                option_d="D选项",
                answer=chr(65 + (i % 4)),  # A, B, C, D cycling
                knowledge_tag="测试知识点",
                text_hash=f"hash_{i}",
            )
            db_session.add(q)
            questions.append(q)
        db_session.commit()
        for q in questions:
            db_session.refresh(q)
        return questions

    def test_get_random_questions(self, db_session):
        """Test random question retrieval."""
        self._create_questions(db_session, count=10)
        service = QuizService(db_session)

        questions = service.get_random_questions(count=3)
        assert len(questions) == 3
        # Ensure answers are NOT included
        for q in questions:
            assert "answer" not in q

    def test_get_random_questions_by_subject(self, db_session):
        """Test random questions filtered by subject."""
        self._create_questions(db_session, count=5)
        # Add a different subject question
        q = Question(
            subject="操作系统",
            question_text="OS题目",
            answer="A",
            text_hash="hash_os_1",
        )
        db_session.add(q)
        db_session.commit()

        service = QuizService(db_session)
        questions = service.get_random_questions(count=10, subject="操作系统")
        for q in questions:
            assert q["subject"] == "操作系统"

    def test_submit_correct_answer(self, db_session):
        """Test submitting a correct answer."""
        questions = self._create_questions(db_session, count=1)
        service = QuizService(db_session)

        # First question has answer "A"
        result = service.submit_answer(questions[0].id, "A")
        assert result.is_correct is True
        assert result.correct_answer == "A"

    def test_submit_wrong_answer(self, db_session):
        """Test submitting a wrong answer."""
        questions = self._create_questions(db_session, count=1)
        service = QuizService(db_session)

        result = service.submit_answer(questions[0].id, "C")
        assert result.is_correct is False

    def test_submit_nonexistent_question(self, db_session):
        """Test submitting answer for non-existent question raises error."""
        service = QuizService(db_session)

        with pytest.raises(QuestionNotFoundError):
            service.submit_answer(99999, "A")

    def test_get_stats_empty(self, db_session):
        """Test stats with no quiz records."""
        service = QuizService(db_session)
        stats = service.get_stats()

        assert stats.total_attempts == 0
        assert stats.accuracy == 0.0

    def test_get_stats_with_records(self, db_session):
        """Test stats after submitting answers."""
        questions = self._create_questions(db_session, count=4)
        service = QuizService(db_session)

        # Submit 2 correct, 2 wrong
        service.submit_answer(questions[0].id, "A")  # correct
        service.submit_answer(questions[1].id, "A")  # wrong (answer is B)
        service.submit_answer(questions[2].id, "C")  # correct
        service.submit_answer(questions[3].id, "A")  # wrong (answer is D)

        stats = service.get_stats()
        assert stats.total_attempts == 4
        assert stats.total_correct == 2
        assert stats.accuracy == pytest.approx(0.5)

    def test_weak_knowledge_tracking(self, db_session):
        """Test that weak knowledge is updated on answer submission."""
        questions = self._create_questions(db_session, count=2)
        service = QuizService(db_session)

        # Submit wrong answers to build up weak knowledge
        service.submit_answer(questions[0].id, "C")  # wrong
        service.submit_answer(questions[1].id, "C")  # wrong

        stats = service.get_stats()
        weak = stats.weak_knowledge
        assert len(weak) > 0
        assert weak[0]["wrong_count"] >= 1


class TestUngradedSubmission:
    """Tests for the key fix: AI-fallback failures must not pollute stats."""

    def _create_unanswered_choice(self, db_session):
        """A choice question with NO answer in DB (triggers AI fallback)."""
        q = Question(
            subject="数据结构",
            question_text="无答案的选择题",
            option_a="A选项",
            option_b="B选项",
            option_c="C选项",
            option_d="D选项",
            question_type="choice",
            answer="",  # no answer → AI fallback
            knowledge_tag="测试知识点",
            text_hash="hash_unanswered",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)
        return q

    def _create_essay(self, db_session):
        """A 综合题 (non-choice) question."""
        q = Question(
            subject="操作系统",
            question_text="请简述进程与线程的区别。",
            question_type="other",  # no options
            answer="",
            knowledge_tag="进程线程",
            text_hash="hash_essay",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)
        return q

    def test_choice_no_answer_ai_fail_leaves_ungraded(self, db_session, monkeypatch):
        """When AI fallback fails, submission must NOT count as wrong."""
        q = self._create_unanswered_choice(db_session)

        # Stub LLM: simulate AI returning an invalid (non A-D) answer → ungraded
        from app.services import quiz_service as qs_module

        class _DummyLLM:
            def is_configured(self):
                return True

            def answer_question(self, *a, **kw):
                return {"answer": "无法确定", "analysis": ""}  # invalid letter

        monkeypatch.setattr(qs_module, "get_llm_service", lambda: _DummyLLM())

        service = QuizService(db_session)
        result = service.submit_answer(q.id, "A")

        assert result.graded is False
        assert result.is_correct is False  # meaningless when not graded
        # Crucially: no record written, no weak-knowledge hit
        stats = service.get_stats()
        assert stats.total_attempts == 0
        assert stats.total_correct == 0
        assert stats.accuracy == 0.0
        assert stats.weak_knowledge == []

    def test_choice_no_answer_ai_success_is_graded(self, db_session, monkeypatch):
        """When AI fallback returns a valid letter, grading proceeds normally."""
        q = self._create_unanswered_choice(db_session)

        from app.services import quiz_service as qs_module

        class _DummyLLM:
            def is_configured(self):
                return True

            def answer_question(self, *a, **kw):
                return {"answer": "B", "analysis": "解析B"}

        monkeypatch.setattr(qs_module, "get_llm_service", lambda: _DummyLLM())

        service = QuizService(db_session)
        result = service.submit_answer(q.id, "B")  # correct per AI

        assert result.graded is True
        assert result.is_correct is True
        assert result.correct_answer == "B"
        # Answer written back to DB
        db_session.refresh(q)
        assert q.answer == "B"
        # Recorded in stats
        stats = service.get_stats()
        assert stats.total_attempts == 1
        assert stats.total_correct == 1

    def test_essay_question_not_graded(self, db_session, monkeypatch):
        """综合题 must never be auto-graded, even though a reference is generated."""
        q = self._create_essay(db_session)

        from app.services import quiz_service as qs_module

        class _DummyLLM:
            def is_configured(self):
                return True

            def answer_essay_question(self, *a, **kw):
                return {"answer": "参考答案正文", "analysis": "解析"}

        monkeypatch.setattr(qs_module, "get_llm_service", lambda: _DummyLLM())

        service = QuizService(db_session)
        result = service.submit_answer(q.id, "进程是资源分配单位...")

        assert result.graded is False
        assert result.analysis is not None
        assert "参考答案" in result.analysis
        # No record, no stats impact
        stats = service.get_stats()
        assert stats.total_attempts == 0
