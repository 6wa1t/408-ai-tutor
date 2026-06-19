"""Wrong Questions API routes — 错题集管理、重做、统计。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import QuestionNotFoundError
from app.services.wrong_question_service import WrongQuestionService

router = APIRouter(prefix="/api/wrong-questions", tags=["错题集"])


# ── Request / Response Schemas ──


class ManualAddRequest(BaseModel):
    question_id: int = Field(..., description="要添加的题目ID")


class ReviewSubmitRequest(BaseModel):
    user_answer: str = Field(..., max_length=50, description="用户答案")


class BatchReviewRequest(BaseModel):
    wrong_ids: list[int] = Field(..., description="要重做的错题ID列表")


class BatchRemoveRequest(BaseModel):
    wrong_ids: list[int] = Field(..., description="要移除的错题ID列表")


# ── List & Stats ──


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """获取错题集统计概览。"""
    service = WrongQuestionService(db)
    return service.get_stats()


@router.get("/chapters")
def get_chapters(
    subject: str = Query(..., description="科目名称"),
    db: Session = Depends(get_db),
):
    """获取某科目下有错题的章节列表。"""
    service = WrongQuestionService(db)
    chapters = service.get_chapters(subject)
    return {"chapters": chapters}


@router.get("/")
def list_wrong_questions(
    subject: str | None = Query(None, description="科目筛选"),
    chapter: str | None = Query(None, description="章节筛选"),
    status: str | None = Query(None, description="状态筛选: correct/wrong/unreviewed"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
):
    """分页获取错题列表。"""
    service = WrongQuestionService(db)
    return service.list_wrong_questions(subject, chapter, status, page, page_size)


# ── Detail ──


@router.get("/{wrong_id}")
def get_detail(
    wrong_id: int,
    db: Session = Depends(get_db),
):
    """获取单条错题详情（含完整题目）。"""
    service = WrongQuestionService(db)
    detail = service.get_detail(wrong_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Wrong question not found")
    return detail


# ── Add / Remove ──


@router.post("/")
def add_wrong_question(
    payload: ManualAddRequest,
    db: Session = Depends(get_db),
):
    """手动添加题目到错题集。"""
    service = WrongQuestionService(db)
    try:
        result = service.add_wrong_question(payload.question_id, source="manual")
        return result
    except QuestionNotFoundError:
        raise HTTPException(status_code=404, detail="Question not found")


@router.delete("/{wrong_id}")
def remove_wrong_question(
    wrong_id: int,
    db: Session = Depends(get_db),
):
    """从错题集中移除。"""
    service = WrongQuestionService(db)
    ok = service.remove_wrong_question(wrong_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Wrong question not found")
    return {"success": True}


@router.post("/batch-remove")
def batch_remove(
    payload: BatchRemoveRequest,
    db: Session = Depends(get_db),
):
    """批量移除错题。"""
    service = WrongQuestionService(db)
    count = service.batch_remove(payload.wrong_ids)
    return {"removed": count}


# ── Re-challenge ──


@router.post("/batch-review")
def get_batch_for_review(
    payload: BatchReviewRequest,
    db: Session = Depends(get_db),
):
    """获取批量重做题目数据（不含答案）。"""
    service = WrongQuestionService(db)
    items = service.get_batch_for_review(payload.wrong_ids)
    return {"items": items, "total": len(items)}


@router.post("/{wrong_id}/review")
def submit_review(
    wrong_id: int,
    payload: ReviewSubmitRequest,
    db: Session = Depends(get_db),
):
    """提交重做答案。"""
    service = WrongQuestionService(db)
    result = service.submit_review(wrong_id, payload.user_answer)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
