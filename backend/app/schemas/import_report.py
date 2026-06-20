"""Pydantic schemas for PDF import reports."""

from datetime import datetime

from pydantic import BaseModel, Field


class QuestionParseResult(BaseModel):
    """Result of parsing a single question from PDF."""

    status: str = Field(..., description="状态: success/skipped/error")
    question_text: str = Field("", description="题目文本摘要")
    error_message: str | None = Field(None, description="错误信息")


class PDFImportResult(BaseModel):
    """Result of importing a single PDF file."""

    filename: str
    total_found: int = Field(0, description="检测到的题目数")
    success_count: int = Field(0, description="成功导入数")
    skipped_count: int = Field(0, description="跳过数(去重)")
    error_count: int = Field(0, description="失败数")
    errors: list[str] = Field(default_factory=list, description="错误详情")
    vlm_used: bool = Field(False, description="是否使用了视觉大模型(VLM)提取")


class ImportReportResponse(BaseModel):
    """Full import report for a directory import."""

    started_at: datetime
    finished_at: datetime | None = None
    total_files: int = 0
    total_questions: int = 0
    total_success: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    file_results: list[PDFImportResult] = Field(default_factory=list)
