"""Garbled text repair service — corrects PUA characters in question database.

Scans all questions for PUA (Private Use Area) characters caused by broken
PDF font encoding, groups them by source PDF, matches each question to its
page via fingerprint comparison, then uses vision LLM to read the correct
symbols from the rendered page image and writes corrections back to DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging_config import get_logger
from app.models.question import Question
from app.services.llm_service import get_llm_service
from app.services.pdf_parser import clean_page_text
from app.services.pua_detector import (
    contains_pua,
    normalize_for_matching,
    strip_pua,
)

logger = get_logger("garbled_text_repair")

# Default directory where the user's source PDFs live (override via PDF_DIR env var)
_DEFAULT_PDF_DIR = os.environ.get("PDF_DIR", str(Path.home()))

# How many leading characters to use for fingerprint matching
_FINGERPRINT_LEN = 40


# ─────────────────────────────────────────────
# Report dataclass
# ─────────────────────────────────────────────

@dataclass
class RepairReport:
    """Tracks progress and results of a repair run."""

    total_affected: int = 0
    total_corrected: int = 0
    total_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    # Per-PDF breakdown
    pdfs_processed: int = 0
    pages_rendered: int = 0
    llm_calls: int = 0

    def summary(self) -> str:
        """Return a human-readable summary of the repair run."""
        lines = [
            "=" * 60,
            "  PUA Garbled Text Repair Report",
            "=" * 60,
            f"  Total affected questions : {self.total_affected}",
            f"  Successfully corrected   : {self.total_corrected}",
            f"  Skipped (no match/error) : {self.total_skipped}",
            f"  Errors encountered       : {len(self.errors)}",
            f"  PDFs processed           : {self.pdfs_processed}",
            f"  Pages rendered           : {self.pages_rendered}",
            f"  LLM correction calls     : {self.llm_calls}",
            "=" * 60,
        ]
        if self.errors:
            lines.append("\nErrors:")
            for i, err in enumerate(self.errors, 1):
                lines.append(f"  {i}. {err}")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# Progress tracker (JSON file for resume)
# ─────────────────────────────────────────────

@dataclass
class _ProgressState:
    """Persisted progress state for resumable repair runs."""

    completed_pages: list[str] = field(default_factory=list)  # "pdf_stem::page_num"
    completed_questions: list[int] = field(default_factory=list)  # question IDs

    def page_key(self, pdf_stem: str, page_num: int) -> str:
        return f"{pdf_stem}::{page_num}"

    def is_page_done(self, pdf_stem: str, page_num: int) -> bool:
        return self.page_key(pdf_stem, page_num) in self.completed_pages

    def mark_page_done(self, pdf_stem: str, page_num: int) -> None:
        key = self.page_key(pdf_stem, page_num)
        if key not in self.completed_pages:
            self.completed_pages.append(key)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "completed_pages": self.completed_pages,
            "completed_questions": self.completed_questions,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> _ProgressState:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                completed_pages=data.get("completed_pages", []),
                completed_questions=data.get("completed_questions", []),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load progress file, starting fresh: {e}")
            return cls()


# ─────────────────────────────────────────────
# Main service
# ─────────────────────────────────────────────

class GarbledTextRepairService:
    """Scan, match, and correct PUA-garbled question text via vision LLM."""

    def __init__(
        self,
        db: Session,
        pdf_dir: str | None = None,
        progress_file: str | None = None,
    ):
        self.db = db
        self.pdf_dir = pdf_dir or _DEFAULT_PDF_DIR
        self.llm = get_llm_service()

        settings = get_settings()
        self.progress_path = Path(
            progress_file or (Path(settings.image_dir).parent / "data" / "repair_progress.json")
        )
        self.progress = _ProgressState.load(self.progress_path)

    # ── Public API ──

    def repair_all(
        self,
        dry_run: bool = False,
        subject_filter: str | None = None,
    ) -> RepairReport:
        """Run the full repair pipeline.

        Args:
            dry_run: If True, only report what would be fixed without touching DB.
            subject_filter: If set, only repair questions of this subject.

        Returns:
            A RepairReport summarising the run.
        """
        report = RepairReport()

        # 1. Find all affected questions
        affected = self._find_affected_questions(subject_filter)
        report.total_affected = len(affected)

        if not affected:
            logger.info("No questions with PUA characters found. Nothing to repair.")
            return report

        logger.info(f"Found {len(affected)} questions with PUA characters")

        if dry_run:
            self._log_dry_run(affected)
            return report

        # 2. Group by source_pdf
        grouped = self._group_by_source_pdf(affected)
        logger.info(f"Affected questions span {len(grouped)} source PDFs")

        # 3. Process each PDF
        for source_pdf_name, questions in grouped.items():
            try:
                self._process_one_pdf(source_pdf_name, questions, report)
            except Exception as e:
                msg = f"Failed to process PDF '{source_pdf_name}': {e}"
                logger.error(msg, exc_info=True)
                report.errors.append(msg)
                report.total_skipped += len(questions)

        # Save final progress
        self.progress.save(self.progress_path)
        return report

    # ── Step 1: Find affected questions ──

    def _find_affected_questions(
        self, subject_filter: str | None
    ) -> list[Question]:
        """Query all questions and filter those containing PUA characters."""
        query = self.db.query(Question)
        if subject_filter:
            query = query.filter(Question.subject == subject_filter)

        all_questions = query.all()
        affected: list[Question] = []

        for q in all_questions:
            fields = [
                q.question_text or "",
                q.option_a or "",
                q.option_b or "",
                q.option_c or "",
                q.option_d or "",
            ]
            if any(contains_pua(f) for f in fields):
                affected.append(q)

        return affected

    def _log_dry_run(self, affected: list[Question]) -> None:
        """Log what would be repaired in dry-run mode."""
        for q in affected:
            pua_fields = []
            if contains_pua(q.question_text or ""):
                pua_fields.append("question_text")
            for letter in ("a", "b", "c", "d"):
                val = getattr(q, f"option_{letter}", "") or ""
                if contains_pua(val):
                    pua_fields.append(f"option_{letter}")
            logger.info(
                f"[DRY-RUN] Question #{q.id} ({q.subject}) — "
                f"PUA in: {', '.join(pua_fields)}"
            )

    # ── Step 2: Group by source PDF ──

    @staticmethod
    def _group_by_source_pdf(questions: list[Question]) -> dict[str, list[Question]]:
        """Group affected questions by their source_pdf field."""
        grouped: dict[str, list[Question]] = defaultdict(list)
        for q in questions:
            key = q.source_pdf or "__unknown__"
            grouped[key].append(q)
        return dict(grouped)

    # ── Step 3: Process one PDF ──

    def _process_one_pdf(
        self,
        source_pdf_name: str,
        questions: list[Question],
        report: RepairReport,
    ) -> None:
        """Full pipeline for a single source PDF."""
        logger.info(
            f"Processing PDF '{source_pdf_name}' with {len(questions)} affected questions"
        )

        # Resolve the actual PDF file path
        pdf_path = self.resolve_source_pdf(source_pdf_name)
        if not pdf_path:
            msg = f"Could not locate source PDF: {source_pdf_name}"
            logger.error(msg)
            report.errors.append(msg)
            report.total_skipped += len(questions)
            return

        # Build page → questions mapping
        page_map = self.build_page_question_map(pdf_path, questions)
        if not page_map:
            msg = f"No page matches found for PDF '{source_pdf_name}'"
            logger.warning(msg)
            report.errors.append(msg)
            report.total_skipped += len(questions)
            return

        report.pdfs_processed += 1
        pdf_stem = Path(pdf_path).stem

        # Process each page that has matched questions
        for page_num, page_questions in sorted(page_map.items()):
            if self.progress.is_page_done(pdf_stem, page_num):
                logger.info(f"Skipping already-completed page {page_num + 1} of {pdf_stem}")
                report.total_corrected += len(page_questions)
                continue

            try:
                self._correct_page_questions(pdf_path, page_num, page_questions, report)
                self.progress.mark_page_done(pdf_stem, page_num)
                self.progress.save(self.progress_path)
            except Exception as e:
                msg = (
                    f"Failed to correct page {page_num + 1} of "
                    f"'{source_pdf_name}': {e}"
                )
                logger.error(msg, exc_info=True)
                report.errors.append(msg)
                report.total_skipped += len(page_questions)

    # ── Step 3a: Resolve source PDF path ──

    def resolve_source_pdf(self, source_pdf_name: str) -> str | None:
        """Search for the source PDF file on disk.

        Uses os.walk to scan the PDF directory, matching filenames in a
        way that is safe for Chinese characters and encoding edge cases.

        Args:
            source_pdf_name: The filename (or partial path) stored in the DB.

        Returns:
            Absolute path to the PDF file, or None if not found.
        """
        if not source_pdf_name or source_pdf_name == "__unknown__":
            return None

        pdf_dir = Path(self.pdf_dir)
        if not pdf_dir.exists():
            logger.warning(f"PDF directory does not exist: {self.pdf_dir}")
            return None

        # Normalize the target name for comparison
        target_basename = Path(source_pdf_name).name.lower()

        # Walk the directory tree
        for dirpath, _dirnames, filenames in os.walk(str(pdf_dir)):
            for fname in filenames:
                if not fname.lower().endswith(".pdf"):
                    continue
                # Match by exact basename (case-insensitive)
                if fname.lower() == target_basename:
                    return os.path.join(dirpath, fname)

        # Fallback: try matching by stem without extension variations
        target_stem = Path(source_pdf_name).stem.lower()
        for dirpath, _dirnames, filenames in os.walk(str(pdf_dir)):
            for fname in filenames:
                if not fname.lower().endswith(".pdf"):
                    continue
                if Path(fname).stem.lower() == target_stem:
                    return os.path.join(dirpath, fname)

        logger.warning(f"PDF file not found on disk: {source_pdf_name}")
        return None

    # ── Step 3b: Build page → question map ──

    def build_page_question_map(
        self,
        pdf_path: str,
        questions: list[Question],
    ) -> dict[int, list[Question]]:
        """Match each affected question to its PDF page via fingerprint comparison.

        Algorithm:
        1. Extract and clean text from each page of the PDF.
        2. For each affected question, compute a fingerprint: strip PUA chars
           and whitespace from the first _FINGERPRINT_LEN characters of
           question_text.
        3. Do the same for each page's cleaned text.
        4. A question matches a page if the page's normalized text contains
           the question's fingerprint.

        Args:
            pdf_path: Absolute path to the source PDF.
            questions: List of affected Question objects to match.

        Returns:
            Dict mapping 0-indexed page number to list of matched questions.
        """
        page_map: dict[int, list[Question]] = defaultdict(list)

        # Extract per-page text
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Cannot open PDF for page mapping: {pdf_path} — {e}")
            return {}

        try:
            page_texts: list[str] = []
            for page in doc:
                raw_text = page.get_text("text")
                cleaned = clean_page_text(raw_text)
                page_texts.append(cleaned)

            # Normalize each page's text for matching
            page_fingerprints: list[str] = []
            for text in page_texts:
                page_fingerprints.append(normalize_for_matching(text))

            # Match each question to a page
            unmatched: list[Question] = []
            for q in questions:
                q_text = q.question_text or ""
                q_fingerprint = normalize_for_matching(q_text)[:_FINGERPRINT_LEN]

                if not q_fingerprint or len(q_fingerprint) < 5:
                    # Fingerprint too short to be reliable
                    unmatched.append(q)
                    continue

                matched_page: int | None = None
                for page_idx, page_fp in enumerate(page_fingerprints):
                    if q_fingerprint in page_fp:
                        matched_page = page_idx
                        break

                if matched_page is not None:
                    page_map[matched_page].append(q)
                else:
                    unmatched.append(q)

            if unmatched:
                logger.warning(
                    f"Could not match {len(unmatched)} questions to pages "
                    f"in '{Path(pdf_path).name}': "
                    f"IDs={[q.id for q in unmatched[:10]]}"
                    f"{'...' if len(unmatched) > 10 else ''}"
                )
        finally:
            doc.close()

        logger.info(
            f"Page mapping for '{Path(pdf_path).name}': "
            f"{sum(len(v) for v in page_map.values())}/{len(questions)} questions "
            f"matched across {len(page_map)} pages"
        )
        return dict(page_map)

    # ── Step 3c: Correct one page's questions via vision LLM ──

    def _correct_page_questions(
        self,
        pdf_path: str,
        page_num: int,
        questions: list[Question],
        report: RepairReport,
    ) -> None:
        """Render page, call LLM for corrections, and apply them to DB."""
        logger.info(
            f"Correcting {len(questions)} questions on page {page_num + 1} "
            f"of '{Path(pdf_path).name}'"
        )

        # Render page to PNG
        image_path = self.llm.pdf_page_to_image(pdf_path, page_num)
        report.pages_rendered += 1

        try:
            # Build question payloads for the LLM
            question_payloads: list[dict[str, Any]] = []
            for q in questions:
                question_payloads.append({
                    "id": q.id,
                    "question_text": q.question_text or "",
                    "option_a": q.option_a or "",
                    "option_b": q.option_b or "",
                    "option_c": q.option_c or "",
                    "option_d": q.option_d or "",
                })

            # Call vision LLM for corrections
            result = self.llm.correct_garbled_text(image_path, question_payloads)
            report.llm_calls += 1

            corrections = result.get("corrections", [])
            if not corrections:
                logger.warning(
                    f"LLM returned no corrections for page {page_num + 1} "
                    f"of '{Path(pdf_path).name}'"
                )
                report.total_skipped += len(questions)
                return

            # Build a lookup by question_id
            correction_map: dict[int, dict] = {}
            for corr in corrections:
                qid = corr.get("question_id")
                if qid is not None:
                    correction_map[int(qid)] = corr

            # Apply corrections to DB
            for q in questions:
                corr = correction_map.get(q.id)
                if corr is None:
                    logger.warning(
                        f"No correction returned for question #{q.id}, skipping"
                    )
                    report.total_skipped += 1
                    continue

                success = self._apply_correction(q, corr)
                if success:
                    report.total_corrected += 1
                    self.progress.completed_questions.append(q.id)
                else:
                    report.total_skipped += 1

        finally:
            # Clean up rendered image
            try:
                img_path = Path(image_path)
                if img_path.exists():
                    img_path.unlink()
            except OSError:
                pass

    # ── Step 3d: Apply a single correction to DB ──

    def _apply_correction(self, question: Question, correction: dict) -> bool:
        """Apply LLM correction to a question record and persist to DB.

        Args:
            question: The ORM Question object to update.
            correction: Dict from LLM with corrected text fields.

        Returns:
            True if the correction was applied successfully and no PUA remains.
        """
        try:
            # Update text fields
            new_text = correction.get("question_text", question.question_text)
            new_a = correction.get("option_a", question.option_a)
            new_b = correction.get("option_b", question.option_b)
            new_c = correction.get("option_c", question.option_c)
            new_d = correction.get("option_d", question.option_d)

            # Handle None values from LLM — keep original if correction is None
            if new_text is None:
                new_text = question.question_text
            if new_a is None:
                new_a = question.option_a
            if new_b is None:
                new_b = question.option_b
            if new_c is None:
                new_c = question.option_c
            if new_d is None:
                new_d = question.option_d

            # Validate: no PUA characters should remain
            all_fields = [
                str(new_text),
                str(new_a or ""),
                str(new_b or ""),
                str(new_c or ""),
                str(new_d or ""),
            ]
            if any(contains_pua(f) for f in all_fields):
                logger.warning(
                    f"Correction for question #{question.id} still contains "
                    f"PUA characters — skipping update"
                )
                return False

            # Apply updates
            question.question_text = str(new_text)
            question.option_a = str(new_a) if new_a else question.option_a
            question.option_b = str(new_b) if new_b else question.option_b
            question.option_c = str(new_c) if new_c else question.option_c
            question.option_d = str(new_d) if new_d else question.option_d

            # Recompute text_hash
            hash_input = question.question_text.strip()
            question.text_hash = hashlib.sha256(
                hash_input.encode("utf-8")
            ).hexdigest()

            self.db.flush()

            logger.info(
                f"Corrected question #{question.id}: "
                f"'{question.question_text[:50]}...'"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to apply correction to question #{question.id}: {e}",
                exc_info=True,
            )
            return False

    # ── Utility ──

    def commit(self) -> None:
        """Commit all pending DB changes."""
        try:
            self.db.commit()
            logger.info("All corrections committed to database")
        except Exception as e:
            self.db.rollback()
            logger.error(f"DB commit failed, rolled back: {e}")
            raise

    def reset_progress(self) -> None:
        """Clear saved progress to allow a fresh repair run."""
        self.progress = _ProgressState()
        if self.progress_path.exists():
            self.progress_path.unlink()
        logger.info("Repair progress reset")
