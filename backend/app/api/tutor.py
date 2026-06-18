"""AI Tutor API routes — DeepSeek powered study assistant.

Endpoints:
- POST /api/tutor/chat     — chat with AI tutor (non-streaming)
- POST /api/tutor/stream   — streaming chat for real-time UI
- GET  /api/tutor/status   — check if LLM is configured
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.llm_service import get_llm_service
from app.schemas.tutor import (
    TutorChatRequest,
    TutorChatResponse,
    TutorStatusResponse,
)

router = APIRouter(prefix="/api/tutor", tags=["AI Tutor"])


@router.get("/status", response_model=TutorStatusResponse)
def get_tutor_status():
    """Check if the LLM API is configured and reachable."""
    llm = get_llm_service()
    configured = llm.is_configured()
    return TutorStatusResponse(
        configured=configured,
        model=llm.model if configured else None,
    )


@router.post("/chat", response_model=TutorChatResponse)
def chat_with_tutor(
    request: TutorChatRequest,
    db: Session = Depends(get_db),
):
    """Send a message to the AI tutor and get a response.

    The tutor has access to 408 exam knowledge and can:
    - Explain concepts from all 4 subjects
    - Analyze wrong answers and weak points
    - Provide study recommendations
    """
    llm = get_llm_service()
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="LLM API未配置，请在.env文件中设置LLM_API_KEY",
        )

    # Build context from question if question_id is provided
    context = ""
    if request.question_id:
        from app.repositories.question_repo import QuestionRepository
        repo = QuestionRepository(db)
        q = repo.get_by_id(request.question_id)
        if q:
            context = (
                f"\n[当前题目] 科目:{q.subject} 章节:{q.chapter}\n"
                f"题目: {q.question_text}\n"
            )
            if q.option_a:
                context += f"A.{q.option_a} B.{q.option_b} C.{q.option_c} D.{q.option_d}\n"
            if q.answer:
                context += f"正确答案: {q.answer}\n"
            if q.analysis:
                context += f"解析: {q.analysis}\n"

    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.extend(request.history)
    messages.append({"role": "user", "content": request.message})

    try:
        reply = llm.chat(
            messages=messages,
            temperature=request.temperature,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM API调用失败: {str(e)}",
        )

    return TutorChatResponse(reply=reply)


@router.post("/stream")
def stream_chat_with_tutor(
    request: TutorChatRequest,
    db: Session = Depends(get_db),
):
    """Stream chat response token by token for real-time UI."""
    llm = get_llm_service()
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="LLM API未配置，请在.env文件中设置LLM_API_KEY",
        )

    context = ""
    if request.question_id:
        from app.repositories.question_repo import QuestionRepository
        repo = QuestionRepository(db)
        q = repo.get_by_id(request.question_id)
        if q:
            context = (
                f"\n[当前题目] 科目:{q.subject} 章节:{q.chapter}\n"
                f"题目: {q.question_text}\n"
            )
            if q.option_a:
                context += f"A.{q.option_a} B.{q.option_b} C.{q.option_c} D.{q.option_d}\n"

    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.extend(request.history)
    messages.append({"role": "user", "content": request.message})

    def event_generator():
        try:
            for token in llm.chat_stream(
                messages=messages,
                temperature=request.temperature,
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
