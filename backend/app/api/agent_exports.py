"""Agent export API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.agent_export import AgentExport
from app.services.agent_export_service import AgentExportService


router = APIRouter(prefix="/api/agent-exports", tags=["Agent exports"])


def _ensure_export_schema() -> None:
    try:
        import app.models  # noqa: F401
        from app.database.schema_sync import sync_agent_knowledge_schema
        from app.database.session import create_tables, engine

        create_tables()
        sync_agent_knowledge_schema(engine)
    except Exception:
        return


@router.post("")
def create_agent_export(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Generate an Agent-readable notes export."""
    _ensure_export_schema()
    return AgentExportService(db).export(limit=limit)


@router.get("")
def list_agent_exports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent Agent export runs."""
    rows = db.query(AgentExport).order_by(AgentExport.created_at.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": row.id,
                "export_root": row.export_root,
                "manifest_path": row.manifest_path,
                "weak_point_count": row.weak_point_count,
                "misconception_count": row.misconception_count,
                "wrong_question_count": row.wrong_question_count,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
