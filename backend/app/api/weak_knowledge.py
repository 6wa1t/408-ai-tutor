"""Weak Knowledge API routes — 薄弱知识点查询与统计。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.quiz_repo import WeakKnowledgeRepository

router = APIRouter(prefix="/api/weak-knowledge", tags=["薄弱知识点"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """获取薄弱知识点汇总统计：总数、平均掌握度、各科目最弱5个知识点。"""
    repo = WeakKnowledgeRepository(db)
    return repo.get_summary()


@router.get("/")
def list_weak_knowledge(
    subject: str | None = Query(None, description="按科目筛选"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    min_wrong: int = Query(0, ge=0, description="最少答错次数"),
    db: Session = Depends(get_db),
):
    """获取薄弱知识点列表，按掌握度从低到高排序。"""
    repo = WeakKnowledgeRepository(db)
    return repo.get_all_filtered(subject=subject, limit=limit, min_wrong=min_wrong)
