"""Question API routes for listing and practice."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.asset_repo import QuestionAssetRepository
from app.repositories.question_repo import QuestionRepository
from app.schemas.question import QuestionListResponse, QuestionResponse

router = APIRouter(prefix="/api/questions", tags=["questions"])

_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _practice_question_text(text: str | None) -> str:
    """Remove markdown image references from practice text."""
    if not text:
        return ""
    cleaned = _MARKDOWN_IMAGE_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _serialize_asset(asset):
    text_content = asset.text_content
    source_type = asset.source_type
    page_no = asset.page_no
    return {
        "id": asset.id,
        "asset_type": asset.asset_type,
        "path": asset.path,
        "content_md": text_content,
        "text_content": text_content,
        "source": source_type,
        "source_type": source_type,
        "page_number": page_no,
        "page_no": page_no,
        "bbox_json": asset.bbox_json,
        "confidence": asset.confidence,
    }


def _serialize_question_for_practice(q, assets=None):
    return {
        "id": q.id,
        "subject": q.subject,
        "chapter": q.chapter,
        "question_text": _practice_question_text(q.question_text),
        "question_type": q.question_type,
        "option_a": q.option_a,
        "option_b": q.option_b,
        "option_c": q.option_c,
        "option_d": q.option_d,
        "image_path": q.image_path,
        "assets": [_serialize_asset(asset) for asset in (assets or [])],
    }


@router.get("", response_model=QuestionListResponse)
def list_questions(
    subject: str | None = Query(None, description="Filter by subject"),
    chapter: str | None = Query(None, description="Filter by chapter"),
    knowledge_tag: str | None = Query(None, description="Filter by knowledge tag"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Rows per page"),
    db: Session = Depends(get_db),
):
    """Get a paginated list of questions with optional filters."""
    repo = QuestionRepository(db)
    skip = (page - 1) * page_size

    items = repo.search(
        subject=subject,
        chapter=chapter,
        knowledge_tag=knowledge_tag,
        skip=skip,
        limit=page_size,
    )
    total = repo.count_search(
        subject=subject,
        chapter=chapter,
        knowledge_tag=knowledge_tag,
    )

    return QuestionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[QuestionResponse.model_validate(q) for q in items],
    )


@router.get("/stats", response_model=dict)
def question_stats(db: Session = Depends(get_db)):
    """Get question count statistics grouped by subject."""
    repo = QuestionRepository(db)
    subject_counts = repo.count_by_subject()
    total = repo.count()
    return {
        "total": total,
        "by_subject": {subject: count for subject, count in subject_counts},
    }


@router.get("/random")
def get_random_questions(
    count: int = Query(10, ge=1, le=50, description="Question count"),
    subject: str | None = Query(None, description="Subject"),
    question_type: str | None = Query(None, description="Question type: choice/other"),
    db: Session = Depends(get_db),
):
    """Get random questions for practice with answers hidden."""
    repo = QuestionRepository(db)
    questions = repo.get_random(count, subject, question_type)
    assets_by_question = QuestionAssetRepository(db).list_for_questions(
        [q.id for q in questions]
    )

    results = [
        _serialize_question_for_practice(q, assets_by_question.get(q.id, []))
        for q in questions
    ]
    return {"count": len(results), "questions": results}


@router.get("/chapters")
def get_chapters(
    subject: str = Query(..., description="Subject"),
    question_type: str | None = Query(None, description="Question type: choice/other"),
    db: Session = Depends(get_db),
):
    """Get ordered chapter list for a subject with question counts."""
    repo = QuestionRepository(db)
    chapters = repo.get_chapters_by_subject(subject, question_type)
    return {
        "subject": subject,
        "chapters": [{"name": name, "count": count} for name, count in chapters],
    }


@router.get("/by_chapter")
def get_questions_by_chapter(
    subject: str = Query(..., description="Subject"),
    chapter: str = Query(..., description="Chapter"),
    question_type: str | None = Query(None, description="Question type: choice/other"),
    db: Session = Depends(get_db),
):
    """Get all questions in a chapter ordered by original source order."""
    repo = QuestionRepository(db)
    questions = repo.get_by_chapter(subject, chapter, question_type)
    assets_by_question = QuestionAssetRepository(db).list_for_questions(
        [q.id for q in questions]
    )

    results = [
        _serialize_question_for_practice(q, assets_by_question.get(q.id, []))
        for q in questions
    ]
    return {
        "subject": subject,
        "chapter": chapter,
        "count": len(results),
        "questions": results,
    }


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(question_id: int, db: Session = Depends(get_db)):
    """Get a single question by ID, including answer and analysis."""
    repo = QuestionRepository(db)
    question = repo.get_by_id(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return QuestionResponse.model_validate(question)
