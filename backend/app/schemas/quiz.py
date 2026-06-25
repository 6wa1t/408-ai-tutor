"""Pydantic schemas for Quiz operations."""

from datetime import datetime

from pydantic import BaseModel, Field


class QuizSubmit(BaseModel):
    """Schema for submitting a quiz answer."""

    question_id: int = Field(..., description="题目ID")
    user_answer: str = Field(..., max_length=50, description="用户答案")


class QuizResult(BaseModel):
    """Result of a quiz submission."""

    question_id: int
    user_answer: str
    correct_answer: str
    is_correct: bool
    graded: bool = Field(
        True,
        description="是否已自动判分。False 表示未判分（综合题或 AI 兜底失败），"
        "此时 is_correct 无意义、不计入统计。",
    )
    analysis: str | None = None
    knowledge_tag: str | None = None
    answer_ref: str | None = None
    answer_source: str | None = None
    answer_confidence: float | None = None
    usable_for_grading: bool | None = None
    misconception_synced: bool = Field(
        True,
        description="误区分析是否成功记录。False 表示辅助任务失败（不影响判分与统计），"
        "前端可据此给出轻提示。",
    )
    wrong_question_synced: bool = Field(
        True,
        description="错题自动入库是否成功。False 表示辅助任务失败（不影响判分与统计），"
        "前端可据此给出轻提示。",
    )


class RandomQuizRequest(BaseModel):
    """Request parameters for getting random quiz questions."""

    subject: str | None = Field(None, description="指定科目")
    count: int = Field(10, ge=1, le=50, description="题目数量")


class QuizStatsResponse(BaseModel):
    """Overall quiz statistics."""

    total_attempts: int = 0
    total_correct: int = 0
    accuracy: float = Field(0.0, description="总正确率")
    subject_stats: list[dict] = Field(default_factory=list, description="各科统计")
    weak_knowledge: list[dict] = Field(default_factory=list, description="薄弱知识点")


class QuizRecordResponse(BaseModel):
    """Single quiz record response."""

    id: int
    question_id: int
    user_answer: str
    is_correct: bool
    create_time: datetime

    model_config = {"from_attributes": True}
