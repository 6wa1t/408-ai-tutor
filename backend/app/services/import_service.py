"""Import Service — orchestrates PDF scanning, parsing, and database storage.

This is the business logic layer that coordinates:
1. PDF file discovery
2. PDF parsing (via PDFParser)
3. Format validation
4. Deduplication
5. Database storage
6. Import report generation
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import PDFImportError
from app.core.logging_config import get_logger
from app.models.question import Question
from app.repositories.question_repo import QuestionRepository
from app.schemas.import_report import PDFImportResult, ImportReportResponse
from app.services.pdf_parser import PDFParser, infer_subject

logger = get_logger("import_service")


class ImportService:
    """Service for importing PDF question banks into the database."""

    def __init__(self, db: Session, parser: PDFParser | None = None):
        self.db = db
        self.repo = QuestionRepository(db)
        self.parser = parser or PDFParser()

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
                question_text=parsed_q.question_text,
                option_a=parsed_q.options.get("A"),
                option_b=parsed_q.options.get("B"),
                option_c=parsed_q.options.get("C"),
                option_d=parsed_q.options.get("D"),
                answer=parsed_q.answer or "",
                answer_ref=parsed_q.answer_ref or None,
                analysis=parsed_q.analysis or None,
                image_path=",".join(parsed_q.image_paths) if parsed_q.image_paths else None,
                source_pdf=filename,
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
        return result

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
