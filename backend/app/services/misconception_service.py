"""Misconception Service — AI-driven error analysis for wrong answers.

When a user answers incorrectly:
1. AI analyzes WHY the user chose the wrong answer
2. Identifies the underlying knowledge gap
3. Generates a remediation strategy

The misconception records are persisted here so they can be read by other
systems (e.g. a desktop agent that pushes them to a FlowUs knowledge base via
MCP). This service deliberately does NOT handle the push itself — that is the
agent's responsibility, so no FlowUs credentials or sync state live here.
"""

from __future__ import annotations

import json
import re

from openai import APIError, RateLimitError, APIConnectionError
from sqlalchemy import func
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.logging_config import get_logger
from app.models.misconception import Misconception
from app.models.question import Question
from app.repositories.quiz_repo import WeakKnowledgeRepository
from app.services.llm_service import get_llm_service

logger = get_logger("misconception_service")


MISCONCEPTION_PROMPT = """你是408考研错题分析专家。请分析以下学生的错题，找出其思维误区。

题目信息：
科目：{subject}
章节：{chapter}
题目：{question_text}
选项：
{options}

学生的答案：{user_answer}（错误）
正确答案：{correct_answer}

请严格按以下JSON格式返回分析结果：
{{
    "misconception_summary": "用1-2句话概括学生的错误思维，说明他为什么会被这个选项误导",
    "knowledge_gap": "指出学生没有掌握的核心知识点，用简短精炼的表述",
    "remediation": "给出针对性的纠正建议和记忆方法"
}}

只返回JSON，不要有其他内容。"""


class MisconceptionService:
    """Service for misconception analysis (错题误区分析)."""

    def __init__(self, db: Session):
        self.db = db

    def analyze_wrong_answer(
        self,
        question: Question,
        user_answer: str,
        correct_answer: str,
    ) -> Misconception | None:
        """Analyze a wrong answer using AI and create a misconception record.

        Returns the created Misconception, or None if analysis fails.
        """
        # Check if misconception already exists for this question
        existing = (
            self.db.query(Misconception)
            .filter(Misconception.question_id == question.id)
            .first()
        )
        if existing:
            existing.frequency += 1
            logger.info(
                f"Updated existing misconception #{existing.id} frequency → {existing.frequency}"
            )
            self.db.commit()
            return existing

        # Build options text for prompt
        options_parts = []
        for letter, attr in [("A", "option_a"), ("B", "option_b"),
                              ("C", "option_c"), ("D", "option_d")]:
            val = getattr(question, attr, None)
            if val:
                options_parts.append(f"{letter}. {val}")

        prompt = MISCONCEPTION_PROMPT.format(
            subject=question.subject,
            chapter=question.chapter or "未知",
            question_text=question.question_text,
            options="\n".join(options_parts),
            user_answer=user_answer,
            correct_answer=correct_answer,
        )

        # Call AI for analysis
        try:
            llm = get_llm_service()
            if not llm.is_configured():
                logger.warning("LLM not configured, creating basic misconception")
                record = self._create_basic_misconception(
                    question, user_answer, correct_answer
                )
                self._ensure_weak_knowledge(question)
                self.db.commit()
                logger.info(
                    f"Created basic misconception #{record.id} for Q#{question.id}"
                )
                return record

            reply = self._call_llm_for_analysis(llm, prompt)
            analysis = self._parse_analysis(reply)

        except (APIError, RateLimitError, APIConnectionError) as e:
            logger.error(f"AI misconception analysis failed after retries: {e}")
            analysis = {
                "misconception_summary": "",
                "knowledge_gap": "",
                "remediation": "",
            }
        except Exception as e:
            logger.error(f"AI misconception analysis unexpected error: {e}")
            analysis = {
                "misconception_summary": "",
                "knowledge_gap": "",
                "remediation": "",
            }

        # Create record
        record = Misconception(
            question_id=question.id,
            subject=question.subject,
            chapter=question.chapter,
            user_answer=user_answer,
            correct_answer=correct_answer,
            misconception_summary=analysis.get("misconception_summary", ""),
            knowledge_gap=analysis.get("knowledge_gap", ""),
            remediation=analysis.get("remediation", ""),
        )
        self.db.add(record)
        self._ensure_weak_knowledge(question)
        self.db.commit()
        logger.info(
            f"Created misconception #{record.id} for Q#{question.id} "
            f"({question.subject}/{question.chapter})"
        )
        return record

    def get_misconceptions(
        self,
        subject: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Misconception]:
        """Query misconception records with filters."""
        query = self.db.query(Misconception)
        if subject:
            query = query.filter(Misconception.subject == subject)
        return query.order_by(Misconception.created_at.desc()).offset(skip).limit(limit).all()

    def count_misconceptions(self, subject: str | None = None) -> int:
        """Count misconception records."""
        query = self.db.query(Misconception)
        if subject:
            query = query.filter(Misconception.subject == subject)
        return query.count()

    def get_summary_by_subject(self) -> list[dict]:
        """Get misconception summary grouped by subject and chapter."""
        results = (
            self.db.query(
                Misconception.subject,
                Misconception.chapter,
                func.count(Misconception.id).label("count"),
                func.sum(Misconception.frequency).label("total_freq"),
            )
            .group_by(Misconception.subject, Misconception.chapter)
            .order_by(Misconception.subject, Misconception.chapter)
            .all()
        )
        return [
            {
                "subject": r.subject,
                "chapter": r.chapter,
                "misconception_count": r.count,
                "total_wrong_attempts": int(r.total_freq),
            }
            for r in results
        ]

    # ── Helpers ──

    def _ensure_weak_knowledge(self, question: Question) -> None:
        """Ensure a weak_knowledge entry exists for this question.

        quiz_service already calls update_stats for questions that have
        knowledge_tags. This method handles the gap: questions WITHOUT
        pre-set tags get a fallback tag derived from subject+chapter so
        every wrong answer contributes to weak knowledge tracking.
        """
        if question.knowledge_tag:
            # quiz_service handles this path — skip to avoid double counting
            return

        # Derive a fallback tag from subject + chapter
        if question.chapter:
            fallback_tag = f"{question.subject}:{question.chapter}"
        else:
            fallback_tag = question.subject

        weak_repo = WeakKnowledgeRepository(self.db)
        weak_repo.update_stats(fallback_tag, is_correct=False)
        logger.debug(
            f"Updated weak_knowledge for untagged question Q#{question.id} "
            f"with fallback tag '{fallback_tag}'"
        )

    @staticmethod
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
    )
    def _call_llm_for_analysis(llm, prompt: str) -> str:
        """Call LLM for misconception analysis with retry on transient API errors."""
        response = llm.client.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": "你是408考研错题分析专家，严格返回JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _parse_analysis(text: str) -> dict:
        """Parse AI analysis JSON response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse misconception analysis: {text[:200]}")
            return {
                "misconception_summary": text[:500],
                "knowledge_gap": "",
                "remediation": "",
            }

    def _create_basic_misconception(
        self,
        question: Question,
        user_answer: str,
        correct_answer: str,
    ) -> Misconception:
        """Create a basic misconception record without AI analysis.

        Does NOT commit — caller is responsible for committing.
        """
        record = Misconception(
            question_id=question.id,
            subject=question.subject,
            chapter=question.chapter,
            user_answer=user_answer,
            correct_answer=correct_answer,
            misconception_summary=f"选了{user_answer}，正确答案是{correct_answer}",
            knowledge_gap=question.chapter or "",
            remediation="建议复习该章节相关知识点",
        )
        self.db.add(record)
        return record
