"""Misconception API routes — query and summarize AI error analysis.

FlowUs push is handled externally by a desktop agent via MCP, so this router
exposes only read/query endpoints. The agent reads misconception records from
here (or directly from the DB) and pushes them to FlowUs itself.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.misconception_service import MisconceptionService

router = APIRouter(prefix="/api/misconceptions", tags=["错题误区"])


@router.get("")
def list_misconceptions(
    subject: str | None = Query(None, description="科目筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get paginated misconception records."""
    svc = MisconceptionService(db)
    skip = (page - 1) * page_size
    items = svc.get_misconceptions(subject=subject, skip=skip, limit=page_size)
    total = svc.count_misconceptions(subject=subject)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": m.id,
                "question_id": m.question_id,
                "subject": m.subject,
                "chapter": m.chapter,
                "user_answer": m.user_answer,
                "correct_answer": m.correct_answer,
                "misconception_summary": m.misconception_summary,
                "knowledge_gap": m.knowledge_gap,
                "remediation": m.remediation,
                "frequency": m.frequency,
                "created_at": m.created_at.isoformat(),
            }
            for m in items
        ],
    }


@router.get("/summary")
def misconception_summary(db: Session = Depends(get_db)):
    """Get misconception summary grouped by subject and chapter."""
    svc = MisconceptionService(db)
    return {"summary": svc.get_summary_by_subject()}


@router.get("/stats")
def misconception_stats(db: Session = Depends(get_db)):
    """Get overall misconception statistics."""
    svc = MisconceptionService(db)
    total = svc.count_misconceptions()
    summary = svc.get_summary_by_subject()

    subjects = {}
    for item in summary:
        subj = item["subject"]
        if subj not in subjects:
            subjects[subj] = {"chapters": 0, "misconceptions": 0, "wrong_attempts": 0}
        subjects[subj]["chapters"] += 1
        subjects[subj]["misconceptions"] += item["misconception_count"]
        subjects[subj]["wrong_attempts"] += item["total_wrong_attempts"]

    return {
        "total_misconceptions": total,
        "by_subject": subjects,
    }
