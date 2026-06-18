"""Question API routes — CRUD and search for questions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories.question_repo import QuestionRepository
from app.schemas.question import QuestionResponse, QuestionListResponse

router = APIRouter(prefix="/api/questions", tags=["题目"])


@router.get("", response_model=QuestionListResponse)
def list_questions(
    subject: str | None = Query(None, description="科目筛选"),
    chapter: str | None = Query(None, description="章节筛选"),
    knowledge_tag: str | None = Query(None, description="知识点标签"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
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
    count: int = Query(10, ge=1, le=50, description="题目数量"),
    subject: str | None = Query(None, description="指定科目"),
    question_type: str | None = Query(None, description="题型: choice/other"),
    db: Session = Depends(get_db),
):
    """Get random questions for practice (answers hidden)."""
    repo = QuestionRepository(db)
    questions = repo.get_random(count, subject, question_type)

    results = []
    for q in questions:
        results.append({
            "id": q.id,
            "subject": q.subject,
            "chapter": q.chapter,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "image_path": q.image_path,
        })
    return {"count": len(results), "questions": results}


@router.get("/chapters")
def get_chapters(
    subject: str = Query(..., description="科目名称"),
    question_type: str | None = Query(None, description="题型: choice/other"),
    db: Session = Depends(get_db),
):
    """Get ordered chapter list for a subject with question counts."""
    repo = QuestionRepository(db)
    chapters = repo.get_chapters_by_subject(subject, question_type)
    return {
        "subject": subject,
        "chapters": [
            {"name": name, "count": count}
            for name, count in chapters
        ],
    }


@router.get("/by_chapter")
def get_questions_by_chapter(
    subject: str = Query(..., description="科目名称"),
    chapter: str = Query(..., description="章节名称"),
    question_type: str | None = Query(None, description="题型: choice/other"),
    db: Session = Depends(get_db),
):
    """Get all questions in a specific chapter, ordered by original PDF order."""
    repo = QuestionRepository(db)
    questions = repo.get_by_chapter(subject, chapter, question_type)

    results = []
    for q in questions:
        results.append({
            "id": q.id,
            "subject": q.subject,
            "chapter": q.chapter,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "image_path": q.image_path,
        })
    return {
        "subject": subject,
        "chapter": chapter,
        "count": len(results),
        "questions": results,
    }


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(question_id: int, db: Session = Depends(get_db)):
    """Get a single question by ID (includes answer and analysis)."""
    repo = QuestionRepository(db)
    question = repo.get_by_id(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return QuestionResponse.model_validate(question)
