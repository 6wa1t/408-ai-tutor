"""Import Service — orchestrates file scanning, parsing, and database storage.

Supports three import modes:
- text_pdf:    PyMuPDF text extraction (fast, free, for text-based PDFs)
- scanned_pdf: Qwen VL Max vision model (for scanned/image-based PDFs)
- markdown:    Direct markdown parsing (recommended, for MinerU-converted files)

This is the business logic layer that coordinates:
1. File discovery (PDF or Markdown)
2. Parsing (via PDFParser or MarkdownParser)
3. Format validation
4. Deduplication
5. Database storage
6. Import report generation
7. Post-processing: image extraction + PUA garbled text repair
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import PDFImportError
from app.core.logging_config import get_logger
from app.models.question import Question
from app.models.question_asset import QuestionAsset
from app.repositories.question_repo import QuestionRepository
from app.schemas.import_report import PDFImportResult, ImportReportResponse
from app.services.image_extractor import ImageExtractionService
from app.services.markdown_parser import MarkdownParser
from app.services.media_paths import copy_asset_to_runtime
from app.services.pdf_parser import PDFParser, PyMuPDFStrategy, infer_subject
from app.services.text_cleaner import clean_question_text, repair_pua_text

logger = get_logger("import_service")

# Valid import modes
IMPORT_MODES = ("text_pdf", "scanned_pdf", "markdown")

# PUA 字符检测和修复已统一到 text_cleaner.py，此处保留检测逻辑用于统计
_PUA_RE = re.compile(r'[\ue000-\uf8ff]')
_PUA_TEXT_FIELDS = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'analysis']


def _has_pua(text: str) -> bool:
    return bool(text and _PUA_RE.search(text))


def _repair_pua_text(text: str) -> str:
    """将PUA字符替换为标准Unicode（委托给text_cleaner）。"""
    return repair_pua_text(text)


def _compute_text_hash(question_text: str) -> str:
    """Compute SHA256 hash of question text for deduplication."""
    return hashlib.sha256(question_text.encode("utf-8")).hexdigest()


class ImportService:
    """Service for importing question banks into the database.

    Supports PDF (text and scanned) and Markdown file imports.
    """

    def __init__(self, db: Session, import_mode: str = "text_pdf",
                 auto_process: bool = True):
        """
        Args:
            db: Database session.
            import_mode: One of "text_pdf", "scanned_pdf", "markdown".
            auto_process: If True, automatically extract images and repair
                PUA garbled text after each file import.
        """
        if import_mode not in IMPORT_MODES:
            raise ValueError(
                f"Invalid import_mode '{import_mode}'. "
                f"Must be one of: {', '.join(IMPORT_MODES)}"
            )

        self.db = db
        self.repo = QuestionRepository(db)
        self.import_mode = import_mode
        self.auto_process = auto_process

        # Build parser based on mode
        if import_mode == "text_pdf":
            self.parser = PDFParser(strategy=PyMuPDFStrategy())
        elif import_mode == "scanned_pdf":
            self.parser = PDFParser(force_vlm=True)
        else:
            # markdown mode — no PDF parser needed
            self.parser = None

        self.md_parser = MarkdownParser() if import_mode == "markdown" else None

    # ── File scanning ──────────────────────────

    def scan_directory(self, directory: str) -> list[str]:
        """Scan a directory for importable files (PDF or Markdown).

        Args:
            directory: Path to the directory to scan.

        Returns:
            List of file paths.

        Raises:
            PDFImportError: If directory does not exist.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise PDFImportError(f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise PDFImportError(f"Not a directory: {directory}")

        if self.import_mode == "markdown":
            # For markdown mode: find .md files (recursively to handle MinerU output)
            files = sorted(str(p) for p in dir_path.rglob("*.md"))
            logger.info(f"Found {len(files)} Markdown files in {directory}")
        else:
            files = sorted(str(p) for p in dir_path.glob("*.pdf"))
            logger.info(f"Found {len(files)} PDF files in {directory}")

        return files

    # ── Single file import ──────────────────────

    def import_file(self, file_path: str) -> PDFImportResult:
        """Import a single file (PDF or Markdown) into the database.

        Dispatches to the correct parser based on import_mode.

        Args:
            file_path: Path to the file.

        Returns:
            PDFImportResult with counts and any errors.
        """
        if self.import_mode == "markdown":
            return self._import_markdown(file_path)
        else:
            return self._import_pdf(file_path)

    def _import_pdf(self, pdf_path: str) -> PDFImportResult:
        """Import a single PDF file."""
        filename = Path(pdf_path).name
        result = PDFImportResult(filename=filename)
        subject = infer_subject(pdf_path)

        logger.info(
            f"Importing PDF [{self.import_mode}]: {filename} "
            f"(detected subject: {subject})"
        )

        try:
            parsed_items = self.parser.parse_with_text_hash(pdf_path)
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            result.errors.append(f"Parse error: {e}")
            result.error_count = 1
            return result

        # Track whether VLM was used
        if self.import_mode == "scanned_pdf" or self.parser.used_vlm:
            result.vlm_used = True
            logger.warning(
                f"[VLM] {filename} 使用了视觉大模型提取，"
                f"共处理约 {len(parsed_items)} 道题，会产生额外 API 费用"
            )

        result.total_found = len(parsed_items)
        self._store_questions(parsed_items, subject, filename, result)

        # Commit this file's imports
        self.repo.commit()
        logger.info(
            f"Import complete for {filename}: "
            f"{result.success_count} new, {result.skipped_count} skipped, "
            f"{result.error_count} errors"
        )

        # Post-processing
        if self.auto_process and result.success_count > 0:
            self._post_process_pdf(pdf_path, filename, result)

        return result

    def _import_markdown(self, md_path: str) -> PDFImportResult:
        """Import a single Markdown file."""
        filename = Path(md_path).name
        result = PDFImportResult(filename=filename)
        subject = infer_subject(md_path)

        # Fallback: detect subject from markdown content if path-based detection failed
        if subject == "未知科目":
            try:
                head = Path(md_path).read_text(encoding="utf-8")[:3000].lower()
                for subj, keywords in [
                    ("计算机组成原理", ["组成原理", "数据通路", "流水线", "cache", "高速缓冲"]),
                    ("计算机网络", ["计算机网络", "计网", "tcp", "osi", "路由"]),
                    ("数据结构", ["数据结构", "二叉树", "链表", "排序算法", "哈希"]),
                    ("操作系统", ["操作系统", "进程管理", "内存管理", "文件系统", "死锁"]),
                ]:
                    if any(kw in head for kw in keywords):
                        subject = subj
                        logger.info(f"Content-based subject detection: {subject}")
                        break
            except Exception:
                pass

        logger.info(f"Importing Markdown: {filename} (detected subject: {subject})")

        try:
            parsed_questions = self.md_parser.parse(md_path)
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            result.errors.append(f"Parse error: {e}")
            result.error_count = 1
            return result

        result.total_found = len(parsed_questions)

        # Compute text hashes and store
        items_with_hash = []
        for q in parsed_questions:
            text_hash = _compute_text_hash(q.question_text)
            items_with_hash.append((q, text_hash))

        self._store_questions(items_with_hash, subject, filename, result)

        # Commit
        self.repo.commit()
        logger.info(
            f"Markdown import complete for {filename}: "
            f"{result.success_count} new, {result.skipped_count} skipped, "
            f"{result.error_count} errors"
        )

        # Post-processing for markdown (only PUA repair, no image extraction)
        if self.auto_process and result.success_count > 0:
            self._post_process_markdown(filename, result)

        return result

    # ── Shared storage logic ────────────────────

    def _store_questions(
        self,
        parsed_items: list,
        subject: str,
        filename: str,
        result: PDFImportResult,
    ) -> None:
        """Store parsed questions into the database with deduplication."""
        for parsed_q, text_hash in parsed_items:
            # Validate: must have question text
            if not parsed_q.question_text.strip():
                result.error_count += 1
                result.errors.append(
                    f"Q#{parsed_q.question_number}: empty question text"
                )
                continue

            # Deduplicate: check text hash
            existing = self.repo.check_duplicate(text_hash)
            if existing:
                result.skipped_count += 1
                logger.debug(f"Skipped duplicate: Q#{parsed_q.question_number}")
                continue

            legacy_image_path = None
            if self.import_mode != "markdown" and parsed_q.image_paths:
                legacy_image_path = ",".join(parsed_q.image_paths)

            # Create ORM object and store
            question = Question(
                subject=subject,
                chapter=parsed_q.section or None,
                knowledge_tag=",".join(parsed_q.knowledge_tag) if parsed_q.knowledge_tag else None,
                question_type="choice" if parsed_q.options else "other",
                question_text=clean_question_text(parsed_q.question_text),
                option_a=clean_question_text(parsed_q.options.get("A")) if parsed_q.options.get("A") else None,
                option_b=clean_question_text(parsed_q.options.get("B")) if parsed_q.options.get("B") else None,
                option_c=clean_question_text(parsed_q.options.get("C")) if parsed_q.options.get("C") else None,
                option_d=clean_question_text(parsed_q.options.get("D")) if parsed_q.options.get("D") else None,
                answer=parsed_q.answer or "",
                answer_ref=parsed_q.answer_ref or None,
                analysis=clean_question_text(parsed_q.analysis) if parsed_q.analysis else None,
                image_path=legacy_image_path,
                source_pdf=filename,
                page_number=parsed_q.page_number,
                exam_year=parsed_q.exam_year or None,
                text_hash=text_hash,
            )
            self.repo.create(question)

            if self.import_mode == "markdown":
                copied_paths = self._copy_markdown_image_assets(
                    parsed_q=parsed_q,
                    question=question,
                    filename=filename,
                )
                if copied_paths:
                    question.image_path = ",".join(copied_paths)

            result.success_count += 1

    # ── Post-processing ─────────────────────────

    def _copy_markdown_image_assets(
        self,
        parsed_q,
        question: Question,
        filename: str,
    ) -> list[str]:
        """Copy Markdown source images into runtime media and create asset rows."""
        copied_paths: list[str] = []
        bank_id = Path(filename).stem

        for idx, source_image_path in enumerate(parsed_q.image_paths or []):
            source_path = Path(source_image_path)
            if not source_path.exists() or not source_path.is_file():
                logger.warning(
                    f"Markdown image source missing, skipped: {source_path}"
                )
                continue

            try:
                rel_path = copy_asset_to_runtime(
                    source_path=source_path,
                    media_root=get_settings().runtime_media_dir,
                    bank_id=bank_id,
                    asset_type="images",
                    filename=f"q{question.id}_{idx}{source_path.suffix}",
                )
            except Exception as e:
                logger.warning(
                    f"Markdown image copy failed, skipped {source_path}: {e}"
                )
                continue

            copied_paths.append(rel_path)
            self.db.add(QuestionAsset(
                question_id=question.id,
                asset_type="image",
                source_type="markdown",
                path=rel_path,
                page_no=parsed_q.page_number,
                confidence=0.9,
            ))

        return copied_paths

    def _post_process_pdf(self, pdf_path: str, filename: str, result: PDFImportResult) -> None:
        """Post-process after PDF import: image extraction + PUA repair.

        - text_pdf mode: extract embedded images + PUA repair
        - scanned_pdf mode: skip image extraction (VLM already handled) + PUA repair
        """
        # ── 1. 提取配图（VLM/scanned模式跳过） ──
        if result.vlm_used:
            logger.info(
                f"[后处理] {filename}: VLM模式，跳过嵌入式图片提取"
            )
        else:
            try:
                extractor = ImageExtractionService(self.db)
                imgs, updated = extractor.extract_from_pdf(pdf_path, dry_run=False)
                if imgs > 0:
                    logger.info(
                        f"[后处理] {filename}: 提取 {imgs} 张图片，关联 {updated} 道题"
                    )
            except Exception as e:
                logger.warning(f"[后处理] {filename} 图片提取失败 (可忽略): {e}")

        # ── 2. 修复PUA乱码 ──
        self._repair_pua(filename)

    def _post_process_markdown(self, filename: str, result: PDFImportResult) -> None:
        """Post-process after Markdown import: PUA repair only (no image extraction)."""
        self._repair_pua(filename)

    def _repair_pua(self, filename: str) -> None:
        """Repair PUA garbled text in recently imported questions."""
        try:
            imported = (
                self.db.query(Question)
                .filter(Question.source_pdf == filename)
                .all()
            )
            pua_fixed = 0
            for q in imported:
                has_any = False
                updates = {}
                for f in _PUA_TEXT_FIELDS:
                    val = getattr(q, f, None) or ""
                    if _has_pua(val):
                        has_any = True
                        updates[f] = _repair_pua_text(val)
                if has_any:
                    for f, repaired in updates.items():
                        setattr(q, f, repaired)
                    pua_fixed += 1

            if pua_fixed > 0:
                self.db.commit()
                logger.info(
                    f"[后处理] {filename}: 修复 {pua_fixed} 道题的PUA乱码"
                )
        except Exception as e:
            logger.warning(f"[后处理] {filename} PUA修复失败 (可忽略): {e}")

    # ── Directory import ────────────────────────

    def import_directory(self, directory: str | None = None) -> ImportReportResponse:
        """Import all files from a directory.

        Args:
            directory: Path to scan. Defaults to configured PDF directory.

        Returns:
            Full import report.
        """
        if directory is None:
            directory = get_settings().pdf_dir

        report = ImportReportResponse(started_at=datetime.now())

        files = self.scan_directory(directory)
        report.total_files = len(files)

        if not files:
            ext = "Markdown" if self.import_mode == "markdown" else "PDF"
            logger.warning(f"No {ext} files found in {directory}")
            report.finished_at = datetime.now()
            return report

        for file_path in files:
            try:
                file_result = self.import_file(file_path)
                report.file_results.append(file_result)
                report.total_success += file_result.success_count
                report.total_skipped += file_result.skipped_count
                report.total_errors += file_result.error_count
                report.total_questions += file_result.total_found
            except Exception as e:
                logger.error(f"Fatal error importing {file_path}: {e}")
                error_result = PDFImportResult(
                    filename=Path(file_path).name,
                    error_count=1,
                    errors=[str(e)],
                )
                report.file_results.append(error_result)
                report.total_errors += 1

        report.finished_at = datetime.now()
        logger.info(
            f"Directory import [{self.import_mode}] finished: "
            f"{report.total_success} new questions from {report.total_files} files"
        )
        return report

    # ── Backward compatibility ──────────────────

    def import_pdf(self, pdf_path: str) -> PDFImportResult:
        """Backward-compatible wrapper. Calls import_file() for PDFs."""
        return self._import_pdf(pdf_path)
