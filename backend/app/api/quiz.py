"""Quiz API routes — answer submission, history, and statistics."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import QuestionNotFoundError
from app.schemas.quiz import QuizSubmit, QuizResult, QuizStatsResponse, QuizRecordResponse
from app.services.quiz_service import QuizService

router = APIRouter(prefix="/api/quiz", tags=["刷题"])


@router.post("/submit", response_model=QuizResult)
def submit_answer(
    payload: QuizSubmit,
    db: Session = Depends(get_db),
):
    """Submit an answer for a question.

    Returns whether the answer is correct, the correct answer,
    and the question's analysis/explanation.
    """
    service = QuizService(db)
    try:
        result = service.submit_answer(payload.question_id, payload.user_answer)
        return result
    except QuestionNotFoundError:
        raise HTTPException(status_code=404, detail="Question not found")


@router.get("/stats", response_model=QuizStatsResponse)
def get_quiz_stats(db: Session = Depends(get_db)):
    """Get overall quiz statistics including accuracy and weak points."""
    service = QuizService(db)
    return service.get_stats()


@router.get("/history", response_model=list[QuizRecordResponse])
def get_quiz_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """Get recent quiz attempt history."""
    service = QuizService(db)
    skip = (page - 1) * page_size
    return service.get_history(skip, page_size)
