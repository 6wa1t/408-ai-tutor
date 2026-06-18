"""Pydantic schemas for Question."""

from datetime import datetime

from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    """Schema for creating a new question (from PDF parser output)."""

    subject: str = Field(..., max_length=50, description="科目")
    chapter: str | None = Field(None, max_length=100, description="章节")
    knowledge_tag: str | None = Field(None, max_length=200, description="知识点标签")
    question_type: str = Field("choice", max_length=20, description="题型")
    question_text: str = Field(..., description="题目正文")
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    answer: str = Field(..., max_length=50, description="正确答案")
    analysis: str | None = Field(None, description="解析")
    image_path: str | None = Field(None, max_length=500, description="图片路径")
    source_pdf: str | None = Field(None, max_length=500, description="来源PDF")


class QuestionResponse(BaseModel):
    """Schema for question API response."""

    id: int
    subject: str
    chapter: str | None = None
    knowledge_tag: str | None = None
    question_type: str
    question_text: str
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    answer: str
    analysis: str | None = None
    image_path: str | None = None
    source_pdf: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionListResponse(BaseModel):
    """Paginated question list response."""

    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
    items: list[QuestionResponse] = Field(default_factory=list)
