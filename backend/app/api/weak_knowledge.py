"""Weak Knowledge API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.quiz_repo import WeakKnowledgeRepository
from app.services.weak_point_service import WeakPointService

router = APIRouter(prefix="/api/weak-knowledge", tags=["weak knowledge"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Get weak knowledge summary statistics."""
    repo = WeakKnowledgeRepository(db)
    return repo.get_summary()


@router.get("/")
def list_weak_knowledge(
    subject: str | None = Query(None, description="Filter by subject"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of rows"),
    min_wrong: int = Query(0, ge=0, description="Minimum wrong count"),
    db: Session = Depends(get_db),
):
    """List weak knowledge entries ordered by mastery."""
    repo = WeakKnowledgeRepository(db)
    return repo.get_all_filtered(subject=subject, limit=limit, min_wrong=min_wrong)


@router.get("/weak-points")
def list_weak_points(
    subject: str | None = Query(None, description="Filter by subject"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of rows"),
    min_wrong: int = Query(1, ge=0, description="Minimum wrong count"),
    db: Session = Depends(get_db),
):
    """Return enriched weak-point previews for the wrong-question page."""
    return {
        "items": WeakPointService(db).list_weak_points(
            subject=subject,
            limit=limit,
            min_wrong=min_wrong,
        )
    }
