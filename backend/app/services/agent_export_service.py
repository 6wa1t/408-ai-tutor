"""Generate Agent-readable weak-point exports."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models.agent_export import AgentExport
from app.models.misconception import Misconception
from app.models.wrong_question import WrongQuestion
from app.services.weak_point_service import WeakPointService


def _safe_name(value: str | None) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (value or "").strip())
    return cleaned or "uncategorized"


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class AgentExportService:
    """Write JSON and Markdown files for desktop Agent and note workflows."""

    def __init__(self, db: Session, export_base: str | Path = "exports/agent_notes"):
        self.db = db
        export_path = Path(export_base)
        if not export_path.is_absolute():
            export_path = PROJECT_ROOT / export_path
        self.export_base = export_path

    def export(self, limit: int = 200) -> dict:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = self.export_base / stamp
        json_dir = root / "json"
        markdown_dir = root / "markdown"
        json_dir.mkdir(parents=True, exist_ok=True)
        markdown_dir.mkdir(parents=True, exist_ok=True)

        weak_points = WeakPointService(self.db).list_weak_points(
            limit=limit,
            min_wrong=1,
        )
        misconceptions = self._serialize_misconceptions()
        wrong_questions = self._serialize_wrong_questions()

        self._write_json(json_dir / "weak_points.json", weak_points)
        self._write_json(json_dir / "misconceptions.json", misconceptions)
        self._write_json(json_dir / "wrong_questions.json", wrong_questions)

        for item in weak_points:
            note_dir = (
                markdown_dir
                / _safe_name(item.get("subject"))
                / _safe_name(item.get("chapter"))
            )
            note_dir.mkdir(parents=True, exist_ok=True)
            note_path = note_dir / f"{_safe_name(item.get('knowledge_tag'))}.md"
            note_path.write_text(self._render_markdown(item), encoding="utf-8")

        manifest = {
            "latest_export": stamp,
            "export_root": self._as_posix(root),
            "weak_point_count": len(weak_points),
            "misconception_count": len(misconceptions),
            "wrong_question_count": len(wrong_questions),
            "created_at": datetime.now().isoformat(),
        }
        manifest_path = self.export_base / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(manifest_path, manifest)

        export_id = self._record_export(
            root=root,
            manifest_path=manifest_path,
            json_dir=json_dir,
            markdown_dir=markdown_dir,
            weak_point_count=len(weak_points),
            misconception_count=len(misconceptions),
            wrong_question_count=len(wrong_questions),
        )
        return {"status": "success", "export_id": export_id, **manifest}

    def _serialize_misconceptions(self) -> list[dict]:
        rows = (
            self.db.query(Misconception)
            .order_by(Misconception.created_at.desc())
            .all()
        )
        return [
            {
                "id": item.id,
                "question_id": item.question_id,
                "subject": item.subject,
                "chapter": item.chapter,
                "user_answer": item.user_answer,
                "correct_answer": item.correct_answer,
                "error_cause": item.error_cause or item.misconception_summary,
                "knowledge_gap": item.knowledge_gap,
                "remediation": item.remediation,
                "related_knowledge_tag": item.related_knowledge_tag,
                "confidence": item.analysis_confidence,
                "model": item.analysis_model,
                "source": item.analysis_source,
            }
            for item in rows
        ]

    def _serialize_wrong_questions(self) -> list[dict]:
        rows = (
            self.db.query(WrongQuestion)
            .order_by(WrongQuestion.added_at.desc())
            .all()
        )
        return [
            {
                "id": item.id,
                "question_id": item.question_id,
                "subject": item.subject,
                "chapter": item.chapter,
                "last_status": item.last_status,
                "review_count": item.review_count,
                "added_at": item.added_at.isoformat(),
                "last_review_at": (
                    item.last_review_at.isoformat() if item.last_review_at else None
                ),
                "question_text": item.question.question_text if item.question else None,
                "question_type": item.question.question_type if item.question else None,
                "answer": item.question.answer if item.question else None,
                "knowledge_tag": item.question.knowledge_tag if item.question else None,
            }
            for item in rows
        ]

    def _record_export(
        self,
        root: Path,
        manifest_path: Path,
        json_dir: Path,
        markdown_dir: Path,
        weak_point_count: int,
        misconception_count: int,
        wrong_question_count: int,
    ) -> int:
        export = AgentExport(
            export_root=self._as_posix(root),
            manifest_path=self._as_posix(manifest_path),
            json_dir=self._as_posix(json_dir),
            markdown_dir=self._as_posix(markdown_dir),
            weak_point_count=weak_point_count,
            misconception_count=misconception_count,
            wrong_question_count=wrong_question_count,
            status="success",
        )
        self.db.add(export)
        self.db.commit()
        return export.id

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )

    @staticmethod
    def _as_posix(path: Path) -> str:
        return str(path).replace("\\", "/")

    @staticmethod
    def _render_markdown(item: dict) -> str:
        actions = item.get("recommended_actions") or [
            "Review related wrong questions"
        ]
        questions = item.get("linked_question_ids") or []
        action_md = "\n".join(f"- {action}" for action in actions)
        question_md = "\n".join(f"- Q{qid}" for qid in questions) or "- None"
        confused = ", ".join(item.get("confused_concepts") or []) or "None"
        mastery = item.get("mastery_score") or 0
        return f"""# {item["knowledge_tag"]}

Subject: {item.get("subject") or "uncategorized"}
Chapter: {item.get("chapter") or "uncategorized"}
Wrong count: {item.get("wrong_count", 0)}
Mastery: {mastery:.0%}

## Common Misconceptions
{item.get("ai_summary") or "No AI summary yet."}

## Confused Concepts
{confused}

## Related Wrong Questions
{question_md}

## Review Actions
{action_md}
"""
