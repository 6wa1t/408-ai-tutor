"""Image Extraction Service — extract embedded images from PDFs and link to questions.

Scans source PDFs for embedded images (diagrams, charts, code snippets, etc.),
saves them to the images directory, and updates the corresponding Question records'
image_path field so the frontend can display them.

Matching strategy:
1. For each PDF page, detect question numbers and their y-coordinates via text dict.
2. For each qualifying image on the page, find the closest question above it.
3. Look up the DB Question record by source_pdf + question_number and update image_path.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging_config import get_logger
from app.models.question import Question
from app.services.pdf_parser import infer_subject, QUESTION_NUM

logger = get_logger("image_extractor")

# Regex to detect question number lines in text dict spans — same logic as QUESTION_NUM
# but applied to individual text lines rather than full-page text.
_QUESTION_LINE_RE = re.compile(r"^\s*(\d{1,4})\s*[.、．]\s*\S")


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────


@dataclass
class ExtractedImage:
    """A single image extracted from a PDF page."""

    page_idx: int
    img_idx: int
    xref: int
    width: int
    height: int
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    data: bytes
    ext: str  # "jpeg", "png", etc.


@dataclass
class ExtractionReport:
    """Summary of a full extraction run across all PDFs."""

    total_pdfs: int = 0
    total_images_extracted: int = 0
    total_questions_updated: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"PDFs: {self.total_pdfs}, "
            f"Images: {self.total_images_extracted}, "
            f"Questions updated: {self.total_questions_updated}, "
            f"Errors: {len(self.errors)}"
        )


# ─────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────


class ImageExtractionService:
    """Extract images from source PDFs and associate them with Question records."""

    MIN_WIDTH: int = 200
    MIN_HEIGHT: int = 150

    def __init__(self, db: Session, image_dir: str | None = None):
        self.db = db
        self.image_dir = image_dir or get_settings().image_dir
        # Ensure the base images/questions directory exists
        Path(self.image_dir, "questions").mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────

    def extract_all(
        self,
        pdf_dir: str | None = None,
        dry_run: bool = False,
    ) -> ExtractionReport:
        """Process all source PDFs found under *pdf_dir*.

        If *pdf_dir* is ``None``, the configured ``pdf_dir`` setting is used.
        When *dry_run* is ``True`` images are scanned but not saved and the DB
        is not modified — useful for verifying detection before a real run.
        """
        report = ExtractionReport()

        if pdf_dir is None:
            pdf_dir = get_settings().pdf_dir

        pdf_files = self._discover_pdfs(pdf_dir)
        report.total_pdfs = len(pdf_files)

        if not pdf_files:
            logger.warning("No PDF files found in %s", pdf_dir)
            return report

        for pdf_path in pdf_files:
            filename = os.path.basename(pdf_path)
            logger.info("Processing PDF: %s", filename)
            try:
                imgs, updated = self.extract_from_pdf(pdf_path, dry_run=dry_run)
                report.total_images_extracted += imgs
                report.total_questions_updated += updated
                logger.info(
                    "  %s -> %d images, %d questions updated",
                    filename,
                    imgs,
                    updated,
                )
            except Exception as exc:
                msg = f"{filename}: {exc}"
                logger.error("  FAILED: %s", msg)
                report.errors.append(msg)

        logger.info("Extraction complete: %s", report.summary())
        return report

    def extract_from_pdf(
        self,
        pdf_path: str,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Extract images from one PDF and link them to questions.

        Returns:
            (images_saved, questions_updated)
        """
        subject = infer_subject(pdf_path)
        source_stem = Path(pdf_path).stem
        source_filename = Path(pdf_path).name

        # Pre-fetch all DB questions that belong to this source PDF, keyed by
        # question_number for fast lookup.
        db_questions_map = self._build_db_questions_map(source_filename)
        if not db_questions_map:
            logger.info(
                "  No DB questions for %s — skipping image extraction", source_filename
            )
            return 0, 0

        doc = fitz.open(pdf_path)
        try:
            images_saved = 0
            questions_updated = 0
            # Track the last question number seen on the previous page so that
            # images appearing *before* any question on a page can be attributed.
            last_q_num_prev_page: int | None = None

            for page_idx in range(len(doc)):
                page = doc[page_idx]

                # 1. Find question positions on this page
                question_positions = self._get_question_positions(page)
                # question_positions: list of (question_number, y_top)

                # 2. Extract qualifying images from this page
                page_images = self._extract_page_images(doc, page_idx)

                # 3. Match images to questions and update DB
                updated = self._match_images_to_questions(
                    page_images=page_images,
                    question_positions=question_positions,
                    page_idx=page_idx,
                    db_questions_map=db_questions_map,
                    subject=subject,
                    source_stem=source_stem,
                    last_q_num_prev_page=last_q_num_prev_page,
                    dry_run=dry_run,
                )
                questions_updated += updated

                if not dry_run:
                    # Save images to disk
                    for img in page_images:
                        self._save_image(img, subject, source_stem)
                    images_saved += len(page_images)
                else:
                    images_saved += len(page_images)

                # Update "last question number" for next page's carry-over logic
                if question_positions:
                    last_q_num_prev_page = question_positions[-1][0]

            if not dry_run:
                self.db.commit()

            return images_saved, questions_updated

        finally:
            doc.close()

    # ── Private helpers ───────────────────────

    def _discover_pdfs(self, pdf_dir: str) -> list[str]:
        """Walk *pdf_dir* recursively and return sorted list of .pdf paths."""
        pdf_files: list[str] = []
        if not os.path.isdir(pdf_dir):
            logger.warning("PDF directory does not exist: %s", pdf_dir)
            return pdf_files
        for root, _dirs, files in os.walk(pdf_dir):
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, fname))
        pdf_files.sort()
        logger.info("Discovered %d PDF files under %s", len(pdf_files), pdf_dir)
        return pdf_files

    def _build_db_questions_map(
        self, source_filename: str
    ) -> dict[int, list[Question]]:
        """Build a mapping ``{question_number: [Question, ...]}`` for all DB
        questions whose ``source_pdf`` matches *source_filename*.

        The question number is inferred from the stored ``question_text`` using
        the same regex pattern used during import (leading "N." / "N、").
        """
        questions: list[Question] = (
            self.db.query(Question)
            .filter(Question.source_pdf == source_filename)
            .order_by(Question.id)
            .all()
        )

        qmap: dict[int, list[Question]] = {}
        for q in questions:
            q_num = self._extract_question_number(q.question_text)
            if q_num is not None:
                qmap.setdefault(q_num, []).append(q)
            else:
                # Fallback: use page_number as a grouping key won't help here,
                # but we still want to keep the record accessible.  Assign a
                # sentinel key so it can still be found by position-based logic.
                logger.debug(
                    "Could not determine question number for Question(id=%d): %s",
                    q.id,
                    q.question_text[:60],
                )

        logger.info(
            "  DB questions for %s: %d (mapped %d by number)",
            source_filename,
            len(questions),
            sum(len(v) for v in qmap.values()),
        )
        return qmap

    @staticmethod
    def _extract_question_number(text: str) -> int | None:
        """Extract leading question number from question text."""
        if not text:
            return None
        m = re.match(r"\s*(\d{1,4})\s*[.、．]", text)
        if m:
            return int(m.group(1))
        return None

    def _extract_page_images(
        self, doc: fitz.Document, page_idx: int
    ) -> list[ExtractedImage]:
        """Extract qualifying images from one page.

        Uses ``page.get_image_info()`` for geometry and
        ``doc.extract_image(xref)`` for the raw pixel data.
        Images below the minimum size threshold are discarded.
        """
        page = doc[page_idx]
        image_info_list = page.get_image_info()  # list[dict]
        results: list[ExtractedImage] = []

        for img_idx, info in enumerate(image_info_list):
            xref: int = info.get("xref", 0)
            width: int = info.get("width", 0)
            height: int = info.get("height", 0)
            bbox_raw = info.get("bbox", (0, 0, 0, 0))

            # Size filter
            if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                continue

            # Extract actual image bytes
            try:
                img_dict = doc.extract_image(xref)
            except Exception as exc:
                logger.warning(
                    "Failed to extract xref=%d on page %d: %s",
                    xref,
                    page_idx,
                    exc,
                )
                continue

            if not img_dict or not img_dict.get("image"):
                continue

            results.append(
                ExtractedImage(
                    page_idx=page_idx,
                    img_idx=img_idx,
                    xref=xref,
                    width=img_dict.get("width", width),
                    height=img_dict.get("height", height),
                    bbox=tuple(bbox_raw),  # type: ignore[arg-type]
                    data=img_dict["image"],
                    ext=img_dict.get("ext", "png"),
                )
            )

        return results

    def _get_question_positions(
        self, page: fitz.Page
    ) -> list[tuple[int, float]]:
        """Detect question numbers and their y-coordinates on a page.

        Returns a list of ``(question_number, y_top)`` tuples sorted by
        ascending y_top (top-to-bottom on the page).

        Uses ``page.get_text("dict")`` which gives a structured breakdown of
        blocks → lines → spans with precise bounding boxes.
        """
        positions: list[tuple[int, float]] = []
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 = text block
                continue
            for line in block.get("lines", []):
                # Reconstruct the full text of this line from its spans
                line_text = "".join(
                    span.get("text", "") for span in line.get("spans", [])
                )
                m = _QUESTION_LINE_RE.match(line_text)
                if m:
                    q_num = int(m.group(1))
                    # line["bbox"] = (x0, y0, x1, y1); y0 is the top
                    y_top = line["bbox"][1]
                    positions.append((q_num, y_top))

        # Sort top-to-bottom (y increases downward in PDF coordinate space)
        positions.sort(key=lambda t: t[1])
        return positions

    def _match_images_to_questions(
        self,
        page_images: list[ExtractedImage],
        question_positions: list[tuple[int, float]],
        page_idx: int,
        db_questions_map: dict[int, list[Question]],
        subject: str,
        source_stem: str,
        last_q_num_prev_page: int | None,
        dry_run: bool,
    ) -> int:
        """Match each image to the question directly above it on the same page.

        If an image appears before any question on the page, it is attributed
        to the last question from the previous page (``last_q_num_prev_page``).

        Returns the number of DB records updated.
        """
        if not page_images:
            return 0

        updated_count = 0

        for img in page_images:
            # The image's top y-coordinate
            img_y = img.bbox[1]

            # Find the closest question whose y_top is <= img_y (i.e., above).
            matched_q_num: int | None = None
            best_distance = float("inf")
            for q_num, q_y in question_positions:
                if q_y <= img_y:
                    distance = img_y - q_y
                    if distance < best_distance:
                        best_distance = distance
                        matched_q_num = q_num

            # If no question above on this page, carry over from previous page
            if matched_q_num is None and last_q_num_prev_page is not None:
                matched_q_num = last_q_num_prev_page

            if matched_q_num is None:
                logger.debug(
                    "  Image page=%d idx=%d: no matching question found",
                    page_idx,
                    img.img_idx,
                )
                continue

            # Look up DB question(s) for this question number
            db_questions = db_questions_map.get(matched_q_num, [])
            if not db_questions:
                logger.debug(
                    "  Image page=%d idx=%d -> Q#%d: no DB record",
                    page_idx,
                    img.img_idx,
                    matched_q_num,
                )
                continue

            # Build the relative image path
            rel_path = self._image_rel_path(
                subject, source_stem, page_idx, img.img_idx, img.ext
            )

            # Update all matching DB records (there may be multiple if question
            # numbers repeat across sections, though unlikely).
            for q in db_questions:
                # Prefer the question whose page_number matches
                if q.page_number is not None and q.page_number != page_idx:
                    # Not on the same page — lower priority but still a candidate
                    # if no better match exists.
                    pass

                if dry_run:
                    logger.info(
                        "  [DRY-RUN] Would link Q(id=%d, #%d page=%d) -> %s",
                        q.id,
                        matched_q_num,
                        q.page_number,
                        rel_path,
                    )
                    updated_count += 1
                    continue

                # Append to existing image_path (comma-separated) if present
                if q.image_path:
                    existing_paths = [
                        p.strip() for p in q.image_path.split(",") if p.strip()
                    ]
                    if rel_path not in existing_paths:
                        existing_paths.append(rel_path)
                        q.image_path = ",".join(existing_paths)
                        updated_count += 1
                else:
                    q.image_path = rel_path
                    updated_count += 1

        return updated_count

    def _save_image(
        self,
        img: ExtractedImage,
        subject: str,
        source_stem: str,
    ) -> str:
        """Write image bytes to disk. Returns the absolute path written."""
        rel_path = self._image_rel_path(
            subject, source_stem, img.page_idx, img.img_idx, img.ext
        )
        abs_path = Path(self.image_dir, rel_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(img.data)
        logger.debug("  Saved image: %s (%d bytes)", abs_path, len(img.data))
        return str(abs_path)

    @staticmethod
    def _image_rel_path(
        subject: str,
        source_stem: str,
        page_idx: int,
        img_idx: int,
        ext: str,
    ) -> str:
        """Build the relative path for a saved image.

        Pattern: ``questions/{subject}/{source_stem}_p{page:03d}_img{idx:03d}.{ext}``

        This is the path stored in ``Question.image_path`` (relative to
        ``image_dir``).
        """
        filename = f"{source_stem}_p{page_idx:03d}_img{img_idx:03d}.{ext}"
        return str(Path("questions") / subject / filename)
