"""Conversations API routes — 对话历史的CRUD管理。"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.conversation import Conversation, ChatMessage

router = APIRouter(prefix="/api/conversations", tags=["对话管理"])


# ── Request / Response schemas (inline, small enough to not need a separate file) ──


class CreateConversationRequest(BaseModel):
    title: str = Field("新对话", max_length=100)


class RenameConversationRequest(BaseModel):
    title: str = Field(..., max_length=100)


class AddMessageRequest(BaseModel):
    role: str = Field(..., description="user / assistant / system")
    content: str = Field(...)


class BookmarksUpdate(BaseModel):
    bookmarks: list[dict] = Field(default_factory=list)


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    bookmarks: list = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("bookmarks", mode="before")
    @classmethod
    def parse_bookmarks(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v or []


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ──


@router.get("/", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    """Get all conversations, newest first."""
    convs = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return convs


@router.post("/", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: CreateConversationRequest,
    db: Session = Depends(get_db),
):
    """Create a new empty conversation."""
    conv = Conversation(title=body.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conv_id}/messages", response_model=list[MessageOut])
def get_messages(conv_id: int, db: Session = Depends(get_db)):
    """Get all messages in a conversation, chronological order."""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return messages


@router.post("/{conv_id}/messages", response_model=MessageOut, status_code=201)
def add_message(
    conv_id: int,
    body: AddMessageRequest,
    db: Session = Depends(get_db),
):
    """Add a message to a conversation. Auto-updates the conversation's updated_at."""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    msg = ChatMessage(
        conversation_id=conv_id,
        role=body.role,
        content=body.content,
    )
    db.add(msg)

    # Touch the conversation's updated_at
    conv.updated_at = datetime.now()
    db.commit()
    db.refresh(msg)
    return msg


@router.patch("/{conv_id}", response_model=ConversationOut)
def rename_conversation(
    conv_id: int,
    body: RenameConversationRequest,
    db: Session = Depends(get_db),
):
    """Rename a conversation."""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    conv.title = body.title
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/{conv_id}", status_code=204)
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    """Delete a conversation and all its messages (CASCADE)."""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    db.delete(conv)
    db.commit()


@router.put("/{conv_id}/bookmarks", response_model=ConversationOut)
def update_bookmarks(
    conv_id: int,
    body: BookmarksUpdate,
    db: Session = Depends(get_db),
):
    """Replace all bookmarks for a conversation."""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    conv.bookmarks = json.dumps(body.bookmarks, ensure_ascii=False)
    conv.updated_at = datetime.now()
    db.commit()
    db.refresh(conv)
    return conv
