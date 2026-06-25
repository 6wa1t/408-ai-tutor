"""Repair legacy Markdown image paths in the runtime database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for path in (PROJECT_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.config import get_settings  # noqa: E402
from app.services.media_paths import copy_asset_to_runtime  # noqa: E402


def _source_candidates(raw_path: str) -> list[Path]:
    normalized = raw_path.replace("\\", "/").strip()
    candidates: list[Path] = []
    if normalized.startswith("/app/"):
        candidates.append(PROJECT_ROOT / normalized.removeprefix("/app/"))
    if normalized.startswith("/"):
        candidates.append(PROJECT_ROOT / normalized.lstrip("/"))
    candidates.append(Path(normalized))
    return candidates


def _first_existing(raw_path: str) -> Path | None:
    for candidate in _source_candidates(raw_path):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def repair(db_path: Path, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    fixed = 0
    missing = 0
    try:
        rows = conn.execute(
            """
            select id, image_path, source_pdf
            from questions
            where image_path like '/app/%'
               or image_path like '%/app/data/mineru_import/images/%'
            order by id
            """
        ).fetchall()

        for row in rows:
            qid = int(row["id"])
            new_paths: list[str] = []
            now = datetime.now().isoformat(sep=" ", timespec="seconds")
            for idx, raw in enumerate((row["image_path"] or "").split(",")):
                raw = raw.strip()
                if not raw:
                    continue
                source = _first_existing(raw)
                if source is None:
                    missing += 1
                    continue
                rel_path = copy_asset_to_runtime(
                    source_path=source,
                    media_root=get_settings().runtime_media_dir,
                    bank_id=Path(row["source_pdf"] or "legacy_markdown").stem,
                    asset_type="images",
                    filename=f"q{qid}_{idx}{source.suffix}",
                )
                new_paths.append(rel_path)
                if not dry_run:
                    exists = conn.execute(
                        """
                        select 1
                        from question_assets
                        where question_id = ? and path = ?
                        """,
                        (qid, rel_path),
                    ).fetchone()
                    if exists is None:
                        conn.execute(
                            """
                            insert into question_assets (
                                question_id, asset_type, path, source_type, confidence, created_at
                            )
                            values (?, 'image', ?, 'legacy_repair', 0.8, ?)
                            """,
                            (qid, rel_path, now),
                        )
            if new_paths and not dry_run:
                conn.execute(
                    "update questions set image_path = ? where id = ?",
                    (",".join(new_paths), qid),
                )
            if new_paths:
                fixed += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return {"fixed_questions": fixed, "missing_images": missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "app_questions.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = repair(Path(args.db), dry_run=args.dry_run)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
