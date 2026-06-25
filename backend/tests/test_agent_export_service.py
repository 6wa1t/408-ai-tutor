import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.base import Base
from app.database.schema_sync import sync_agent_knowledge_schema
from app.config import PROJECT_ROOT
from app.models.misconception import Misconception
from app.models.question import Question
from app.models.weak_knowledge import WeakKnowledge
from app.models.wrong_question import WrongQuestion
from app.services.agent_export_service import AgentExportService


def test_export_writes_manifest_json_markdown_and_record(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(bind=engine)
    sync_agent_knowledge_schema(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    question = Question(
        subject="计算机组成原理",
        chapter="Cache",
        question_text="组号如何计算？",
        question_type="choice",
        answer="A",
        knowledge_tag="CO:Cache:组相联",
    )
    db.add(question)
    db.flush()
    db.add(
        WeakKnowledge(
            knowledge_tag="CO:Cache:组相联",
            wrong_count=4,
            correct_count=1,
            mastery_score=0.2,
        )
    )
    db.add(
        Misconception(
            question_id=question.id,
            subject="计算机组成原理",
            chapter="Cache",
            user_answer="B",
            correct_answer="A",
            misconception_summary="组相联映射字段拆分不清",
            knowledge_gap="Cache 地址字段",
            remediation="重画字段划分",
        )
    )
    db.add(
        WrongQuestion(
            question_id=question.id,
            subject="计算机组成原理",
            chapter="Cache",
            last_status="wrong",
            review_count=1,
        )
    )
    db.flush()
    db.execute(
        text(
            """
            update weak_knowledge
            set subject = :subject,
                chapter = :chapter,
                ai_summary = :summary,
                recommended_actions_json = :actions
            where knowledge_tag = :tag
            """
        ),
        {
            "subject": "计算机组成原理",
            "chapter": "Cache",
            "summary": "混淆组号与块内偏移。",
            "actions": json.dumps(["画地址划分图"], ensure_ascii=False),
            "tag": "CO:Cache:组相联",
        },
    )
    db.execute(
        text(
            """
            update misconceptions
            set error_cause = :cause,
                confused_concepts_json = :concepts,
                recommended_actions_json = :actions,
                related_knowledge_tag = :tag,
                analysis_confidence = :confidence,
                analysis_model = :model,
                analysis_source = :source
            where question_id = :question_id
            """
        ),
        {
            "cause": "混淆组号与块内偏移",
            "concepts": json.dumps(["组号", "块内偏移"], ensure_ascii=False),
            "actions": json.dumps(["画地址划分图"], ensure_ascii=False),
            "tag": "CO:Cache:组相联",
            "confidence": 0.8,
            "model": "deepseek-chat",
            "source": "ai",
            "question_id": question.id,
        },
    )
    db.commit()

    monkeypatch.setattr(
        "app.services.agent_export_service.datetime",
        type(
            "FixedDateTime",
            (),
            {
                "now": staticmethod(
                    lambda: __import__("datetime").datetime(2026, 6, 24, 12, 0, 0)
                )
            },
        ),
    )

    result = AgentExportService(
        db, export_base=tmp_path / "exports" / "agent_notes"
    ).export()

    root = tmp_path / "exports" / "agent_notes" / "20260624-120000"
    manifest = json.loads(
        (tmp_path / "exports" / "agent_notes" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    weak_points = json.loads((root / "json" / "weak_points.json").read_text("utf-8"))
    misconceptions = json.loads(
        (root / "json" / "misconceptions.json").read_text("utf-8")
    )
    wrong_questions = json.loads(
        (root / "json" / "wrong_questions.json").read_text("utf-8")
    )
    note_path = (
        root
        / "markdown"
        / "计算机组成原理"
        / "Cache"
        / "CO_Cache_组相联.md"
    )

    assert result["status"] == "success"
    assert manifest["latest_export"] == "20260624-120000"
    assert manifest["weak_point_count"] == 1
    assert manifest["misconception_count"] == 1
    assert manifest["wrong_question_count"] == 1
    assert weak_points[0]["recommended_actions"] == ["画地址划分图"]
    assert misconceptions[0]["error_cause"] == "混淆组号与块内偏移"
    assert wrong_questions[0]["question_text"] == "组号如何计算？"
    assert note_path.exists()
    assert "混淆组号与块内偏移。" in note_path.read_text(encoding="utf-8")
    export_count = db.execute(text("select count(*) from agent_exports")).scalar_one()
    assert export_count == 1


def test_default_export_base_is_project_root_relative(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    service = AgentExportService(db)

    assert service.export_base == PROJECT_ROOT / "exports" / "agent_notes"
