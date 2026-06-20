"""Conversation ORM models — 对话历史和聊天消息持久化。"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Conversation(Base):
    """对话表 — 每次与AI助教的独立对话会话。"""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(
        String(100), nullable=False, default="新对话", comment="对话标题"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )
    bookmarks: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]", comment="书签JSON"
    )

    # Relationship: one conversation has many messages
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class ChatMessage(Base):
    """聊天消息表 — 对话中的每条消息（用户或AI）。"""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_conversation_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属对话ID",
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="消息角色: user/assistant/system"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    # Relationship back-reference
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', conv={self.conversation_id})>"
