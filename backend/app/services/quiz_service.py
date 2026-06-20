"""Quiz Service — business logic for quiz operations.

Handles:
- Random question selection
- Answer submission and validation (with AI fallback for missing answers)
- Statistics computation
- Weak knowledge tracking
"""

from sqlalchemy.orm import Session

from app.core.exceptions import QuestionNotFoundError
from app.core.logging_config import get_logger
from app.models.question import Question
from app.repositories.question_repo import QuestionRepository
from app.repositories.quiz_repo import QuizRepository, WeakKnowledgeRepository
from app.schemas.quiz import (
    QuizResult,
    QuizStatsResponse,
    QuizRecordResponse,
)
from app.services.llm_service import get_llm_service
from app.services.misconception_service import MisconceptionService

logger = get_logger("quiz_service")


class QuizService:
    """Service for quiz operations (刷题, 答题, 统计)."""

    def __init__(self, db: Session):
        self.db = db
        self.question_repo = QuestionRepository(db)
        self.quiz_repo = QuizRepository(db)
        self.weak_repo = WeakKnowledgeRepository(db)

    def get_random_questions(
        self,
        count: int = 10,
        subject: str | None = None,
    ) -> list[dict]:
        """Get random questions for a quiz session.

        Args:
            count: Number of questions to retrieve.
            subject: Optional subject filter.

        Returns:
            List of question dicts (without answers — answer is hidden).
        """
        questions = self.question_repo.get_random(count, subject)
        logger.info(f"Selected {len(questions)} random questions (subject={subject})")

        results = []
        for q in questions:
            results.append({
                "id": q.id,
                "subject": q.subject,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d,
                "image_path": q.image_path,
                # Note: answer is intentionally NOT included
            })
        return results

    def submit_answer(
        self,
        question_id: int,
        user_answer: str,
    ) -> QuizResult:
        """Submit a user's answer and return the result.

        Grading rules:
        - 选择题 (choice): 若题库有答案则直接判分；否则调 DeepSeek 现场作答、回写库后再判分。
          AI 兜底失败时本次**不判分**（graded=False），不计入正确率与薄弱知识点，避免污染统计。
        - 综合题/其他 (other): 无客观标准答案，不自动判分（graded=False），仅提供 AI 生成的
          参考答案与解析供用户自行对照。

        Args:
            question_id: The question being answered.
            user_answer: The user's selected answer.

        Returns:
            QuizResult with correctness, correct answer, analysis, and a `graded`
            flag indicating whether the answer was actually graded.

        Raises:
            QuestionNotFoundError: If question_id doesn't exist.
        """
        question = self.question_repo.get_by_id(question_id)
        if question is None:
            raise QuestionNotFoundError(
                f"Question not found: id={question_id}"
            )

        correct_answer = (question.answer or "").strip()
        analysis = question.analysis or ""
        is_choice = self._is_choice_question(question)

        # Only choice questions are auto-gradable
        if is_choice and not correct_answer:
            correct_answer, analysis = self._fetch_ai_answer(question, analysis)
        elif not is_choice and not analysis:
            # 综合题无客观答案，不判分；但若库中尚无解析，调 AI 生成参考答案供用户对照
            analysis = self._fetch_essay_reference(question)

        # Determine grading outcome
        graded = False
        is_correct = False
        if is_choice and correct_answer:
            graded = True
            is_correct = user_answer.strip().upper() == correct_answer.upper()

        # Auxiliary-task success flags (default True = no notice shown).
        # Only flipped to False inside the graded-wrong-answer branch below.
        # Declared here so the return statement is well-defined for ungraded
        # submissions (综合题 / AI 兜底失败) as well.
        misconception_synced = True
        wrong_question_synced = True

        # Only record attempts that were actually graded.
        # Ungraded submissions (综合题 or AI 兜底失败) must NOT pollute accuracy
        # or weak-knowledge statistics.
        if graded:
            self.quiz_repo.create_record(question_id, user_answer, is_correct)

            if question.knowledge_tag:
                for tag in question.knowledge_tag.split(","):
                    tag = tag.strip()
                    if tag:
                        self.weak_repo.update_stats(tag, is_correct)

            # Wrong answer (with a real correct answer) → generate misconception analysis
            # These are best-effort auxiliary tasks: failure must NOT block the quiz
            # result. We capture success/failure flags so the frontend can surface a
            # gentle notice (the user otherwise has no way to know auto-collection
            # silently failed).
            if not is_correct:
                try:
                    msvc = MisconceptionService(self.db)
                    msvc.analyze_wrong_answer(question, user_answer, correct_answer)
                except Exception as e:
                    misconception_synced = False
                    logger.error(
                        f"Misconception analysis failed for Q#{question_id}: {e}",
                        exc_info=True,
                    )

                # Auto-add to wrong question collection
                try:
                    from app.services.wrong_question_service import WrongQuestionService
                    wq_svc = WrongQuestionService(self.db)
                    wq_svc.auto_add(question)
                except Exception as e:
                    wrong_question_synced = False
                    logger.error(
                        f"Wrong question auto-add failed for Q#{question_id}: {e}",
                        exc_info=True,
                    )

        self.db.commit()

        logger.info(
            f"Answer submitted: Q#{question_id}, "
            f"type={'choice' if is_choice else 'other'}, graded={graded}, "
            f"user={user_answer}, correct={correct_answer or '<none>'}, "
            f"match={is_correct if graded else 'n/a'}"
        )

        return QuizResult(
            question_id=question_id,
            user_answer=user_answer,
            correct_answer=correct_answer or "(暂无答案)",
            is_correct=is_correct,
            graded=graded,
            analysis=analysis or None,
            knowledge_tag=question.knowledge_tag,
            answer_ref=question.answer_ref or None,
            misconception_synced=misconception_synced,
            wrong_question_synced=wrong_question_synced,
        )

    # ── Helpers ──

    @staticmethod
    def _is_choice_question(question: Question) -> bool:
        """A question is auto-gradable only if it has options (选择题)."""
        return bool(
            question.question_type == "choice"
            and (question.option_a or question.option_b
                 or question.option_c or question.option_d)
        )

    def _fetch_ai_answer(
        self,
        question: Question,
        existing_analysis: str,
    ) -> tuple[str, str]:
        """Ask DeepSeek to solve a choice question with no DB answer.

        On success the answer (and analysis if missing) are written back to the
        database for future attempts. Returns (answer, analysis).

        On any failure returns ("", existing_analysis) so the caller leaves the
        submission ungraded rather than treating it as wrong.
        """
        logger.info(f"Q#{question.id} has no answer, requesting AI solution...")
        try:
            llm = get_llm_service()
            if not llm.is_configured():
                logger.warning("LLM not configured, cannot generate answer")
                return "", existing_analysis

            options = {}
            for letter, attr in [("A", "option_a"), ("B", "option_b"),
                                 ("C", "option_c"), ("D", "option_d")]:
                val = getattr(question, attr, None)
                if val:
                    options[letter] = val

            result = llm.answer_question(
                question.question_text,
                options=options or None,
                subject=question.subject,
            )

            ai_answer = (result.get("answer", "") or "").strip().upper()
            ai_analysis = result.get("analysis", "") or ""

            if ai_answer not in ("A", "B", "C", "D"):
                logger.warning(
                    f"AI returned invalid answer for Q#{question.id}: {ai_answer!r}; "
                    f"leaving ungraded"
                )
                return "", existing_analysis

            # Persist for future use
            question.answer = ai_answer
            if ai_analysis and not existing_analysis:
                question.analysis = ai_analysis
            self.db.commit()

            logger.info(f"AI answered Q#{question.id}: {ai_answer}")
            return ai_answer, existing_analysis or ai_analysis

        except Exception as e:
            logger.error(f"AI answer generation failed for Q#{question.id}: {e}")
            return "", existing_analysis

    def _fetch_essay_reference(self, question: Question) -> str:
        """Generate a reference answer for a 综合题 (non-choice question).

        综合题没有客观标准答案，不判分；这里只为用户提供 AI 参考解答。
        On failure returns "" so the caller just leaves analysis empty.
        """
        try:
            llm = get_llm_service()
            if not llm.is_configured():
                logger.warning("LLM not configured, cannot generate essay reference")
                return ""

            result = llm.answer_essay_question(
                question.question_text,
                subject=question.subject,
            )
            ref_answer = (result.get("answer", "") or "").strip()
            ref_analysis = (result.get("analysis", "") or "").strip()

            if not ref_answer:
                return ""

            combined = ref_answer
            if ref_analysis:
                combined += f"\n\n**解析：** {ref_analysis}"

            # Persist for future attempts
            question.analysis = combined
            self.db.commit()
            logger.info(f"AI reference generated for essay Q#{question.id}")
            return combined
        except Exception as e:
            logger.error(f"AI essay reference failed for Q#{question.id}: {e}")
            return ""

    def get_stats(self) -> QuizStatsResponse:
        """Get overall quiz statistics.

        Returns:
            QuizStatsResponse with accuracy, subject breakdown, and weak points.
        """
        total, correct = self.quiz_repo.get_total_stats()
        accuracy = correct / total if total > 0 else 0.0

        subject_stats = self.quiz_repo.get_subject_stats()

        weak_items = self.weak_repo.get_weakest(limit=10)
        weak_knowledge = [
            {
                "tag": wk.knowledge_tag,
                "wrong_count": wk.wrong_count,
                "correct_count": wk.correct_count,
                "mastery_score": round(wk.mastery_score, 2),
            }
            for wk in weak_items
        ]

        return QuizStatsResponse(
            total_attempts=total,
            total_correct=correct,
            accuracy=round(accuracy, 4),
            subject_stats=subject_stats,
            weak_knowledge=weak_knowledge,
        )

    def get_history(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[QuizRecordResponse]:
        """Get quiz attempt history."""
        records = self.quiz_repo.get_history(skip, limit)
        return [QuizRecordResponse.model_validate(r) for r in records]
