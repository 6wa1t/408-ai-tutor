"""Small SQLite schema syncs for local-first runtime upgrades."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


MISCONCEPTION_COLUMNS = {
    "error_cause": "TEXT",
    "confused_concepts_json": "TEXT",
    "correct_reasoning_path": "TEXT",
    "recommended_actions_json": "TEXT",
    "related_knowledge_tag": "VARCHAR(200)",
    "analysis_confidence": "FLOAT",
    "analysis_model": "VARCHAR(100)",
    "analysis_source": "VARCHAR(50)",
}

WEAK_KNOWLEDGE_COLUMNS = {
    "subject": "VARCHAR(64)",
    "chapter": "VARCHAR(128)",
    "ai_summary": "TEXT",
    "recommended_actions_json": "TEXT",
}


def _add_missing_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table)}
    missing = [
        (name, ddl_type) for name, ddl_type in columns.items() if name not in existing
    ]
    if not missing:
        return

    with engine.begin() as conn:
        for name, ddl_type in missing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def sync_agent_knowledge_schema(engine: Engine) -> None:
    """Add Phase 3 columns to existing local SQLite databases."""
    _add_missing_columns(engine, "misconceptions", MISCONCEPTION_COLUMNS)
    _add_missing_columns(engine, "weak_knowledge", WEAK_KNOWLEDGE_COLUMNS)
