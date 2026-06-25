"""Weak-point aggregation for UI previews and Agent exports."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.misconception import Misconception
from app.models.question import Question
from app.models.weak_knowledge import WeakKnowledge


def _loads_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return [value.strip()] if value.strip() else []
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    if isinstance(data, str) and data.strip():
        return [data.strip()]
    return []


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


class WeakPointService:
    """Build enriched weak-point records from runtime learning data."""

    def __init__(self, db: Session):
        self.db = db

    def list_weak_points(
        self,
        subject: str | None = None,
        limit: int = 50,
        min_wrong: int = 1,
    ) -> list[dict]:
        query = self.db.query(WeakKnowledge)
        if min_wrong > 0:
            query = query.filter(WeakKnowledge.wrong_count >= min_wrong)
        rows = query.order_by(WeakKnowledge.mastery_score.asc()).limit(limit).all()
        items = [self._serialize(row) for row in rows]
        if subject:
            items = [item for item in items if item.get("subject") == subject]
        return items

    def _serialize(self, weak: WeakKnowledge) -> dict:
        weak_extra = self._weak_extra(weak)
        subject = weak_extra.get("subject")
        chapter = weak_extra.get("chapter")
        ai_summary = weak_extra.get("ai_summary") or ""
        actions = _loads_list(weak_extra.get("recommended_actions_json"))

        misconceptions = self._misconceptions_for(weak.knowledge_tag)
        confused: list[str] = []
        question_ids: list[int] = []
        summaries: list[str] = []

        for item in misconceptions:
            extra = self._misconception_extra(item)
            if item.question_id not in question_ids:
                question_ids.append(item.question_id)
            summary = item.misconception_summary or extra.get("error_cause") or ""
            if summary:
                summaries.append(summary)
            _append_unique(confused, _loads_list(extra.get("confused_concepts_json")))
            _append_unique(actions, _loads_list(extra.get("recommended_actions_json")))
            subject = subject or item.subject
            chapter = chapter or item.chapter

        if not subject or not chapter:
            question = (
                self.db.query(Question)
                .filter(Question.knowledge_tag == weak.knowledge_tag)
                .first()
            )
            if question:
                subject = subject or question.subject
                chapter = chapter or question.chapter
                if question.id not in question_ids:
                    question_ids.append(question.id)

        return {
            "id": weak.id,
            "knowledge_tag": weak.knowledge_tag,
            "subject": subject,
            "chapter": chapter,
            "wrong_count": weak.wrong_count,
            "correct_count": weak.correct_count,
            "mastery_score": weak.mastery_score,
            "ai_summary": ai_summary or next((s for s in summaries if s), ""),
            "misconception_count": len(misconceptions),
            "confused_concepts": confused,
            "recommended_actions": actions,
            "linked_question_ids": sorted(set(question_ids)),
        }

    def _misconceptions_for(self, knowledge_tag: str) -> list[Misconception]:
        return (
            self.db.query(Misconception)
            .filter(Misconception.related_knowledge_tag == knowledge_tag)
            .order_by(Misconception.created_at.desc())
            .all()
        )

    def _weak_extra(self, weak: WeakKnowledge) -> dict:
        values = {
            "subject": getattr(weak, "subject", None),
            "chapter": getattr(weak, "chapter", None),
            "ai_summary": getattr(weak, "ai_summary", None),
            "recommended_actions_json": getattr(weak, "recommended_actions_json", None),
        }
        return values

    def _misconception_extra(self, item: Misconception) -> dict:
        values = {
            "error_cause": getattr(item, "error_cause", None),
            "confused_concepts_json": getattr(item, "confused_concepts_json", None),
            "recommended_actions_json": getattr(item, "recommended_actions_json", None),
            "related_knowledge_tag": getattr(item, "related_knowledge_tag", None),
            "analysis_confidence": getattr(item, "analysis_confidence", None),
            "analysis_model": getattr(item, "analysis_model", None),
            "analysis_source": getattr(item, "analysis_source", None),
        }
        return values
