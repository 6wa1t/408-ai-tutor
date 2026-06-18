"""Pydantic schemas for AI Tutor API."""

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""
    role: str = Field(..., description="Message role: user/assistant/system")
    content: str = Field(..., description="Message text content")


class TutorChatRequest(BaseModel):
    """Request body for chat with AI tutor."""
    message: str = Field(..., description="Current user message")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Previous conversation history",
    )
    question_id: int | None = Field(
        None,
        description="Optional question ID for context-aware tutoring",
    )
    temperature: float = Field(
        0.7,
        ge=0,
        le=2,
        description="Sampling temperature",
    )


class TutorChatResponse(BaseModel):
    """Response from AI tutor."""
    reply: str = Field(..., description="AI tutor's reply")


class TutorStatusResponse(BaseModel):
    """Status of LLM service."""
    configured: bool = Field(..., description="Whether LLM API is configured")
    model: str | None = Field(None, description="Current model name")
