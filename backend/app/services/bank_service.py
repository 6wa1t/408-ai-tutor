"""Bank Service — manages pre-built question banks for sharing.

Pre-built banks are curated, verified question sets stored as:
  question_banks/
  ├── manifest.json          # Index of all available banks
  ├── 数据结构/
  │   ├── metadata.json      # Subject, count, source description
  │   └── questions.db       # SQLite with same schema as main DB
  └── ...

Workflow:
1. User imports & verifies questions locally
2. User runs export to create bank packages
3. Banks are uploaded to GitHub for other users
4. Other users select banks to import via UI
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, get_settings
from app.core.logging_config import get_logger
from app.models.answer_candidate import AnswerCandidate
from app.models.bank_import import BankImport
from app.models.question import Question
from app.models.question_asset import QuestionAsset
from app.repositories.question_repo import QuestionRepository
from app.services.media_paths import copy_asset_to_runtime, normalize_relative_media_path
from app.services.text_cleaner import clean_question_text

logger = get_logger("bank_service")

# Bank directory location
BANKS_DIR = PROJECT_ROOT / "question_banks"
MANIFEST_FILE = BANKS_DIR / "manifest.json"


def _table_rows(conn, table_name: str) -> list[dict]:
    """Return all rows from an optional package table."""
    exists = conn.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=:table_name"
        ),
        {"table_name": table_name},
    ).fetchone()
    if not exists:
        return []

    rows = conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
    return [dict(row._mapping) for row in rows]


def _group_by_question_hash(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        text_hash = row.get("question_text_hash") or row.get("text_hash")
        if text_hash:
            grouped.setdefault(text_hash, []).append(row)
    return grouped


def _asset_runtime_group(asset_type: str | None) -> str:
    groups = {
        "image": "images",
        "table": "tables",
        "diagram": "diagrams",
        "code": "code",
        "formula": "formula",
    }
    return groups.get((asset_type or "").strip().lower(), asset_type or "assets")


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _coerce_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_package_file(bank_path: Path, rel_path: str | None) -> Path | None:
    safe_rel = normalize_relative_media_path(rel_path)
    if not safe_rel:
        return None

    source_file = bank_path / safe_rel
    bank_root = bank_path.resolve(strict=False)
    resolved = source_file.resolve(strict=False)
    try:
        resolved.relative_to(bank_root)
    except ValueError:
        return None
    return source_file


def _candidate_raw_payload(candidate: dict) -> str | None:
    raw_payload = candidate.get("raw_payload")
    payload: dict = {}
    if raw_payload:
        try:
            loaded = json.loads(raw_payload)
            if isinstance(loaded, dict):
                payload.update(loaded)
            else:
                return str(raw_payload)
        except (TypeError, json.JSONDecodeError):
            return str(raw_payload)

    for key in ("model", "uncertainty_reason"):
        value = candidate.get(key)
        if value not in (None, ""):
            payload[key] = value

    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


class BankInfo:
    """Simple data class for bank metadata."""

    def __init__(self, id: str, name: str, subject: str,
                 count: int = 0, version: str = "1.0.0",
                 path: str = "", description: str = ""):
        self.id = id
        self.name = name
        self.subject = subject
        self.count = count
        self.version = version
        self.path = path
        self.description = description

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "count": self.count,
            "version": self.version,
            "path": self.path,
            "description": self.description,
        }


class BankService:
    """Service for managing pre-built question banks."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = QuestionRepository(db)

    # ── List available banks ────────────────────

    def list_banks(self) -> list[dict]:
        """List all available pre-built question banks.

        Returns:
            List of bank info dicts.
        """
        if not MANIFEST_FILE.exists():
            logger.info("No manifest.json found — no pre-built banks available")
            return []

        try:
            data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            banks = data.get("banks", [])
            logger.info(f"Found {len(banks)} pre-built banks in manifest")
            return banks
        except Exception as e:
            logger.error(f"Failed to read manifest.json: {e}")
            return []

    # ── Import a bank into main database ────────

    def import_bank(self, bank_id: str) -> dict:
        """Import questions from a pre-built bank into the main database.

        Args:
            bank_id: The bank identifier from manifest.json.

        Returns:
            Dict with import stats: total, imported, skipped.
        """
        banks = self.list_banks()
        bank_meta = None
        for b in banks:
            if b.get("id") == bank_id:
                bank_meta = b
                break

        if not bank_meta:
            raise ValueError(f"Bank not found: {bank_id}")

        bank_path = BANKS_DIR / bank_meta.get("path", bank_id)
        db_file = bank_path / "bank.db"

        if not db_file.exists():
            legacy_db_file = bank_path / "questions.db"
            if legacy_db_file.exists():
                db_file = legacy_db_file
            else:
                raise FileNotFoundError(
                    f"Bank database not found: {db_file}"
                )

        logger.info(f"Importing bank '{bank_meta.get('name', bank_id)}' from {db_file}")

        # Open bank's SQLite database
        bank_engine = create_engine(f"sqlite:///{db_file}")
        imported = 0
        skipped = 0
        total = 0

        try:
            with bank_engine.connect() as conn:
                assets_by_hash = _group_by_question_hash(
                    _table_rows(conn, "question_assets")
                )
                candidates_by_hash = _group_by_question_hash(
                    _table_rows(conn, "answer_candidates")
                )

                # Read all questions from bank
                rows = conn.execute(text(
                    "SELECT subject, chapter, knowledge_tag, question_type, "
                    "question_text, option_a, option_b, option_c, option_d, "
                    "answer, answer_ref, analysis, image_path, source_pdf, "
                    "page_number, exam_year, text_hash "
                    "FROM questions"
                )).fetchall()

                total = len(rows)
                logger.info(f"Bank contains {total} questions")

                for row in rows:
                    row_dict = dict(row._mapping)
                    text_hash = row_dict.get("text_hash")

                    # Deduplication check
                    if text_hash and self.repo.check_duplicate(text_hash):
                        skipped += 1
                        continue

                    question = Question(
                        subject=row_dict.get("subject", "未知科目"),
                        chapter=row_dict.get("chapter"),
                        knowledge_tag=row_dict.get("knowledge_tag"),
                        question_type=row_dict.get("question_type", "choice"),
                        question_text=clean_question_text(
                            row_dict.get("question_text", "")
                        ),
                        option_a=clean_question_text(row_dict.get("option_a")) if row_dict.get("option_a") else None,
                        option_b=clean_question_text(row_dict.get("option_b")) if row_dict.get("option_b") else None,
                        option_c=clean_question_text(row_dict.get("option_c")) if row_dict.get("option_c") else None,
                        option_d=clean_question_text(row_dict.get("option_d")) if row_dict.get("option_d") else None,
                        answer=row_dict.get("answer", ""),
                        answer_ref=row_dict.get("answer_ref"),
                        analysis=clean_question_text(row_dict.get("analysis")) if row_dict.get("analysis") else None,
                        image_path=row_dict.get("image_path"),
                        source_pdf=row_dict.get("source_pdf", f"bank:{bank_id}"),
                        page_number=row_dict.get("page_number"),
                        exam_year=row_dict.get("exam_year"),
                        text_hash=text_hash,
                    )
                    self.repo.create(question)
                    self._import_assets_for_question(
                        bank_id=bank_id,
                        bank_path=bank_path,
                        question=question,
                        assets=assets_by_hash.get(text_hash, []),
                    )
                    self._import_candidates_for_question(
                        question=question,
                        candidates=candidates_by_hash.get(text_hash, []),
                    )
                    imported += 1

            self.db.add(BankImport(
                bank_id=bank_id,
                source_type="built_in",
                source_path=str(db_file),
                status="completed",
                total_questions=total,
                imported_questions=imported,
                error_message=f"skipped={skipped}" if skipped else None,
            ))
            self.repo.commit()
            logger.info(
                f"Bank import complete: {imported} imported, "
                f"{skipped} skipped (duplicates)"
            )

        finally:
            bank_engine.dispose()

        return {
            "bank_id": bank_id,
            "bank_name": bank_meta.get("name", bank_id),
            "total": total,
            "imported": imported,
            "skipped": skipped,
        }

    # ── Export current database to bank packages ─

    def _import_assets_for_question(
        self,
        bank_id: str,
        bank_path: Path,
        question: Question,
        assets: list[dict],
    ) -> None:
        """Import package assets for one newly inserted question."""
        for asset in assets:
            asset_type = asset.get("asset_type") or "image"
            source_file = _safe_package_file(bank_path, asset.get("path"))
            runtime_path = ""
            if source_file and source_file.exists() and source_file.is_file():
                runtime_path = copy_asset_to_runtime(
                    source_path=source_file,
                    media_root=get_settings().runtime_media_dir,
                    bank_id=bank_id,
                    asset_type=_asset_runtime_group(asset_type),
                    filename=source_file.name,
                )

            self.db.add(QuestionAsset(
                question_id=question.id,
                asset_type=asset_type,
                source_type=(
                    asset.get("source_type")
                    or asset.get("source")
                    or "bank"
                ),
                path=runtime_path,
                page_no=asset.get("page_no", asset.get("page_number")),
                bbox_json=asset.get("bbox_json"),
                text_content=asset.get("text_content", asset.get("content_md")),
                checksum=asset.get("checksum"),
                confidence=_coerce_float(asset.get("confidence")),
            ))

    def _import_candidates_for_question(
        self,
        question: Question,
        candidates: list[dict],
    ) -> None:
        """Import package answer candidates for one newly inserted question."""
        for candidate in candidates:
            answer_text = candidate.get("answer_text", candidate.get("answer", ""))
            is_verified = candidate.get("is_verified")
            if is_verified is None:
                is_verified = candidate.get("usable_for_grading")

            self.db.add(AnswerCandidate(
                question_id=question.id,
                source=candidate.get("source") or "bank",
                answer_text=answer_text or "",
                explanation=candidate.get(
                    "explanation",
                    candidate.get("analysis_md"),
                ),
                confidence=_coerce_float(candidate.get("confidence")),
                is_verified=_coerce_bool(is_verified),
                raw_payload=_candidate_raw_payload(candidate),
            ))

    def export_bank(self, subject: str, bank_name: str = "",
                    description: str = "") -> dict:
        """Export questions from the main database into a shareable bank package.

        Args:
            subject: Subject to export (e.g., "数据结构").
            bank_name: Display name for the bank.
            description: Description of the bank's source.

        Returns:
            Dict with export stats.
        """
        # Query questions for this subject
        questions = (
            self.db.query(Question)
            .filter(Question.subject == subject)
            .all()
        )

        if not questions:
            raise ValueError(f"No questions found for subject: {subject}")

        # Create bank directory
        safe_name = subject.replace(" ", "_")
        bank_dir = BANKS_DIR / safe_name
        bank_dir.mkdir(parents=True, exist_ok=True)

        bank_id = safe_name.lower().replace(" ", "-")
        version = "1.0.0"
        question_count = len(questions)
        has_media = any((q.image_path or "").strip() for q in questions)
        has_partial_answers = any((q.answer or "").strip() for q in questions)
        qc_status = "passed_with_warnings"

        # Create bank SQLite database
        bank_db_path = bank_dir / "bank.db"
        bank_engine = create_engine(f"sqlite:///{bank_db_path}")

        # Create table schema
        with bank_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    chapter TEXT,
                    knowledge_tag TEXT,
                    question_type TEXT NOT NULL DEFAULT 'choice',
                    question_text TEXT NOT NULL,
                    option_a TEXT,
                    option_b TEXT,
                    option_c TEXT,
                    option_d TEXT,
                    answer TEXT DEFAULT '',
                    answer_ref TEXT,
                    analysis TEXT,
                    image_path TEXT,
                    source_pdf TEXT,
                    page_number INTEGER,
                    exam_year TEXT,
                    text_hash TEXT,
                    created_at TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS question_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_text_hash TEXT,
                    asset_type TEXT NOT NULL,
                    path TEXT,
                    source TEXT,
                    page_number INTEGER,
                    bbox_json TEXT,
                    content_md TEXT,
                    checksum TEXT,
                    confidence REAL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS answer_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_text_hash TEXT,
                    source TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    explanation TEXT,
                    confidence REAL,
                    is_verified INTEGER DEFAULT 0,
                    raw_payload TEXT
                )
            """))
            conn.commit()

        # Insert questions
        exported = 0
        with bank_engine.connect() as conn:
            for q in questions:
                conn.execute(text("""
                    INSERT INTO questions
                    (subject, chapter, knowledge_tag, question_type,
                     question_text, option_a, option_b, option_c, option_d,
                     answer, answer_ref, analysis, image_path, source_pdf,
                     page_number, exam_year, text_hash, created_at)
                    VALUES
                    (:subject, :chapter, :knowledge_tag, :question_type,
                     :question_text, :option_a, :option_b, :option_c, :option_d,
                     :answer, :answer_ref, :analysis, :image_path, :source_pdf,
                     :page_number, :exam_year, :text_hash, :created_at)
                """), {
                    "subject": q.subject,
                    "chapter": q.chapter,
                    "knowledge_tag": q.knowledge_tag,
                    "question_type": q.question_type,
                    "question_text": q.question_text,
                    "option_a": q.option_a,
                    "option_b": q.option_b,
                    "option_c": q.option_c,
                    "option_d": q.option_d,
                    "answer": q.answer or "",
                    "answer_ref": q.answer_ref,
                    "analysis": q.analysis,
                    "image_path": q.image_path,
                    "source_pdf": q.source_pdf,
                    "page_number": q.page_number,
                    "exam_year": q.exam_year,
                    "text_hash": q.text_hash,
                    "created_at": q.created_at.isoformat() if q.created_at else datetime.now().isoformat(),
                })
                exported += 1
            conn.commit()

        # Export question assets and copy media files
        asset_count = 0
        media_dir = bank_dir / "media" / "images"
        media_dir.mkdir(parents=True, exist_ok=True)

        with bank_engine.connect() as conn:
            for q in questions:
                if not q.text_hash:
                    continue
                assets = self.db.query(QuestionAsset).filter(
                    QuestionAsset.question_id == q.id
                ).all()
                for asset in assets:
                    bank_asset_path = ""
                    if asset.path:
                        src_file = PROJECT_ROOT / "images" / asset.path
                        if src_file.exists() and src_file.is_file():
                            dest_name = src_file.name
                            dest_file = media_dir / dest_name
                            if not dest_file.exists():
                                shutil.copy2(src_file, dest_file)
                            bank_asset_path = f"media/images/{dest_name}"

                    conn.execute(text("""
                        INSERT INTO question_assets
                        (question_text_hash, asset_type, path, source,
                         page_number, bbox_json, content_md, checksum, confidence)
                        VALUES
                        (:question_text_hash, :asset_type, :path, :source,
                         :page_number, :bbox_json, :content_md, :checksum, :confidence)
                    """), {
                        "question_text_hash": q.text_hash,
                        "asset_type": asset.asset_type,
                        "path": bank_asset_path,
                        "source": asset.source_type,
                        "page_number": asset.page_no,
                        "bbox_json": asset.bbox_json,
                        "content_md": asset.text_content,
                        "checksum": asset.checksum,
                        "confidence": asset.confidence,
                    })
                    asset_count += 1

            # Export answer candidates (AI-graded answer cache)
            candidate_count = 0
            for q in questions:
                if not q.text_hash:
                    continue
                candidates = self.db.query(AnswerCandidate).filter(
                    AnswerCandidate.question_id == q.id
                ).all()
                for cand in candidates:
                    conn.execute(text("""
                        INSERT INTO answer_candidates
                        (question_text_hash, source, answer_text, explanation,
                         confidence, is_verified, raw_payload)
                        VALUES
                        (:question_text_hash, :source, :answer_text, :explanation,
                         :confidence, :is_verified, :raw_payload)
                    """), {
                        "question_text_hash": q.text_hash,
                        "source": cand.source,
                        "answer_text": cand.answer_text,
                        "explanation": cand.explanation,
                        "confidence": cand.confidence,
                        "is_verified": 1 if cand.is_verified else 0,
                        "raw_payload": cand.raw_payload,
                    })
                    candidate_count += 1

            conn.commit()

        bank_engine.dispose()

        # Create metadata.json
        metadata = {
            "id": bank_id,
            "name": bank_name or f"王道{subject}",
            "subject": subject,
            "count": exported,
            "question_count": question_count,
            "version": version,
            "description": description or f"从本地数据库导出的{subject}题库",
            "has_media": asset_count > 0,
            "has_partial_answers": any((q.answer or "").strip() for q in questions),
            "asset_count": asset_count,
            "answer_candidate_count": candidate_count,
            "qc_status": qc_status,
            "exported_at": datetime.now().isoformat(),
        }
        (bank_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Update manifest.json
        self._update_manifest(
            bank_id=bank_id,
            name=metadata["name"],
            subject=subject,
            count=exported,
            question_count=question_count,
            version=version,
            path=safe_name,
            description=metadata["description"],
            has_media=asset_count > 0,
            has_partial_answers=any((q.answer or "").strip() for q in questions),
            qc_status=qc_status,
        )

        logger.info(
            f"Exported {exported} questions ({asset_count} assets, "
            f"{candidate_count} answer candidates) for '{subject}' to {bank_dir}"
        )

        return {
            "subject": subject,
            "count": exported,
            "asset_count": asset_count,
            "candidate_count": candidate_count,
            "path": str(bank_dir),
            "bank_db_path": str(bank_db_path),
        }

    def _update_manifest(self, bank_id: str, name: str, subject: str,
                         count: int, question_count: int, version: str,
                         path: str, description: str, has_media: bool,
                         has_partial_answers: bool, qc_status: str) -> None:
        """Update or create manifest.json with a bank entry."""
        BANKS_DIR.mkdir(parents=True, exist_ok=True)

        manifest = {"banks": []}
        if MANIFEST_FILE.exists():
            try:
                manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Update existing or add new
        updated = False
        for bank in manifest.get("banks", []):
            if bank.get("id") == bank_id:
                bank["name"] = name
                bank["subject"] = subject
                bank["count"] = count
                bank["question_count"] = question_count
                bank["path"] = path
                bank["description"] = description
                bank["version"] = version
                bank["has_media"] = has_media
                bank["has_partial_answers"] = has_partial_answers
                bank["qc_status"] = qc_status
                updated = True
                break

        if not updated:
            manifest.setdefault("banks", []).append({
                "id": bank_id,
                "name": name,
                "subject": subject,
                "count": count,
                "question_count": question_count,
                "version": version,
                "path": path,
                "description": description,
                "has_media": has_media,
                "has_partial_answers": has_partial_answers,
                "qc_status": qc_status,
            })

        MANIFEST_FILE.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
