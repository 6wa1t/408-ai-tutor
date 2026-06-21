"""Import Service — orchestrates PDF scanning, parsing, and database storage.

This is the business logic layer that coordinates:
1. PDF file discovery
2. PDF parsing (via PDFParser)
3. Format validation
4. Deduplication
5. Database storage
6. Import report generation
7. Post-processing: image extraction + PUA garbled text repair
"""

import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import PDFImportError
from app.core.logging_config import get_logger
from app.models.question import Question
from app.repositories.question_repo import QuestionRepository
from app.schemas.import_report import PDFImportResult, ImportReportResponse
from app.services.image_extractor import ImageExtractionService
from app.services.pdf_parser import PDFParser, infer_subject
from app.services.text_cleaner import clean_question_text

logger = get_logger("import_service")

# ── PUA字符修复映射表 ──────────────────────────
# PDF使用PMExtra自定义字体编码数学符号，存储在Unicode私用区(PUA U+F0xx)
# 此映射表将其替换为标准Unicode，无需依赖外部字体

_PUA_PAIRED_REPLACEMENTS = [
    ('\uf0ee', '(', ')'),         # 圆括号: O(n²)
    ('\uf0f6', '[', ']'),         # 方括号: A[0..n]
    ('\uf0f4', '|', '|'),         # 绝对值: |V| > |E|
    ('\uf0f7', '\u230a', '\u230b'),  # 下取整: ⌊x⌋
    ('\uf0f8', '\u2308', '\u2309'),  # 上取整: ⌈x⌉
]

_PUA_SINGLE_REPLACEMENTS = {
    '\uf0e0': '',                 # ⟨ 冗余左尖括号
    '\uf0e1': '',                 # 分隔符（冗余）
    '\uf0e2': '',                 # ⟩ 冗余右尖括号
    '\uf00a': "'",                # ′ 上标/撇号
    '\uf0e8': '\u23a7',           # ⎧ 左花括号上段
    '\uf0e9': '\u23ab',           # ⎫ 右花括号上段
    '\uf0ea': '\u23aa',           # ⎪ 花括号延伸
    '\uf0e3': '\u23a7',           # ⎧ 分段函数左括号
    '\uf0e4': '\u222a',           # ∪ 并集
    '\uf0b1': '\u2211',           # ∑ 求和符号
    '\uf0dc': '\u0305',           # ̅ 组合上划线(布尔补)
    '\uf0fb': '\u23df',           # ⏟ 下花括号
    '\uf0fc': '\u23df',
    '\uf0fd': '\u23df',
}

_PUA_RE = re.compile(r'[\ue000-\uf8ff]')
_PUA_TEXT_FIELDS = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'analysis']


def _has_pua(text: str) -> bool:
    return bool(text and _PUA_RE.search(text))


def _repair_pua_text(text: str) -> str:
    """将PUA字符替换为标准Unicode等价符号。"""
    if not text:
        return text
    # 配对括号修复: 先匹配成对出现的pua+pua(中间有空白)
    for pua_ch, open_ch, close_ch in _PUA_PAIRED_REPLACEMENTS:
        pattern = re.escape(pua_ch) + r'\s+' + re.escape(pua_ch)
        text = re.sub(pattern, open_ch + close_ch, text)
        text = text.replace(pua_ch, open_ch)
    # 单字符替换
    for pua_ch, replacement in _PUA_SINGLE_REPLACEMENTS.items():
        text = text.replace(pua_ch, replacement)
    return text


class ImportService:
    """Service for importing PDF question banks into the database."""

    def __init__(self, db: Session, parser: PDFParser | None = None,
                 force_vlm: bool = False, auto_process: bool = True):
        """
        Args:
            db: Database session.
            parser: Optional custom parser.
            force_vlm: Force VLM vision model for PDF extraction.
            auto_process: If True, automatically extract images and repair
                PUA garbled text after each PDF import.
        """
        self.db = db
        self.repo = QuestionRepository(db)
        self.parser = parser or PDFParser(force_vlm=force_vlm)
        self.auto_process = auto_process

    def scan_directory(self, directory: str) -> list[str]:
        """Scan a directory for PDF files.

        Args:
            directory: Path to the directory to scan.

        Returns:
            List of PDF file paths.

        Raises:
            PDFImportError: If directory does not exist.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise PDFImportError(f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise PDFImportError(f"Not a directory: {directory}")

        pdf_files = sorted(str(p) for p in dir_path.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")
        return pdf_files

    def import_pdf(self, pdf_path: str) -> PDFImportResult:
        """Import a single PDF file into the database.

        Flow: parse → validate → deduplicate → store

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            PDFImportResult with counts and any errors.
        """
        filename = Path(pdf_path).name
        result = PDFImportResult(filename=filename)
        subject = infer_subject(pdf_path)

        logger.info(f"Importing PDF: {filename} (detected subject: {subject})")

        try:
            parsed_items = self.parser.parse_with_text_hash(pdf_path)
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            result.errors.append(f"Parse error: {e}")
            result.error_count = 1
            return result

        # Track whether VLM fallback was used
        if self.parser.used_vlm:
            result.vlm_used = True
            logger.warning(
                f"[VLM] {filename} 使用了视觉大模型提取，"
                f"共处理约 {len(parsed_items)} 道题，会产生额外 API 费用"
            )

        result.total_found = len(parsed_items)

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
                image_path=",".join(parsed_q.image_paths) if parsed_q.image_paths else None,
                source_pdf=filename,
                page_number=parsed_q.page_number,
                exam_year=parsed_q.exam_year or None,
                text_hash=text_hash,
            )
            self.repo.create(question)
            result.success_count += 1

        # Commit this file's imports
        self.repo.commit()
        logger.info(
            f"Import complete for {filename}: "
            f"{result.success_count} new, {result.skipped_count} skipped, "
            f"{result.error_count} errors"
        )

        # ── 自动后处理：提取图片 + 修复PUA ──
        if self.auto_process and result.success_count > 0:
            self._post_process(pdf_path, filename, result)

        return result

    # ── 后处理 ──────────────────────────────────

    def _post_process(self, pdf_path: str, filename: str, result: PDFImportResult) -> None:
        """导入后自动处理：提取图片 + 修复PUA乱码。

        在 import_pdf 提交入库后自动调用，不会阻断导入流程。
        """
        # ── 1. 提取配图 ──
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
        try:
            # 查找刚导入的题目中哪些含PUA字符
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
                self.db.flush()
                logger.info(
                    f"[后处理] {filename}: 修复 {pua_fixed} 道题的PUA乱码"
                )
        except Exception as e:
            logger.warning(f"[后处理] {filename} PUA修复失败 (可忽略): {e}")

    def import_directory(self, directory: str | None = None) -> ImportReportResponse:
        """Import all PDFs from a directory.

        Args:
            directory: Path to scan. Defaults to configured PDF directory.

        Returns:
            Full import report.
        """
        if directory is None:
            directory = get_settings().pdf_dir

        report = ImportReportResponse(started_at=datetime.now())

        pdf_files = self.scan_directory(directory)
        report.total_files = len(pdf_files)

        if not pdf_files:
            logger.warning(f"No PDF files found in {directory}")
            report.finished_at = datetime.now()
            return report

        for pdf_path in pdf_files:
            try:
                file_result = self.import_pdf(pdf_path)
                report.file_results.append(file_result)
                report.total_success += file_result.success_count
                report.total_skipped += file_result.skipped_count
                report.total_errors += file_result.error_count
                report.total_questions += file_result.total_found
            except Exception as e:
                logger.error(f"Fatal error importing {pdf_path}: {e}")
                error_result = PDFImportResult(
                    filename=Path(pdf_path).name,
                    error_count=1,
                    errors=[str(e)],
                )
                report.file_results.append(error_result)
                report.total_errors += 1

        report.finished_at = datetime.now()
        logger.info(
            f"Directory import finished: {report.total_success} new questions "
            f"from {report.total_files} files"
        )
        return report
