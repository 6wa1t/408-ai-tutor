"""Answer Extraction Service — Phase 4 framework.

Uses LLM vision capabilities to extract answers and analysis
from scanned original textbook PDFs (原书PDF).

Workflow:
1. Render PDF pages to images (200 DPI)
2. Send images to LLM vision API for OCR + extraction
3. Parse structured JSON response
4. Match extracted answers to questions in the database (by question text hash)
5. Update Question.answer and Question.analysis fields
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.question import Question
from app.repositories.question_repo import QuestionRepository
from app.services.llm_service import get_llm_service

logger = get_logger("answer_extractor")


class AnswerExtractor:
    """Extract answers from original textbook PDFs using vision LLM."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = QuestionRepository(db)
        self.llm = get_llm_service()

    def extract_from_pdf(
        self,
        pdf_path: str,
        subject: str,
        page_range: tuple[int, int] | None = None,
    ) -> dict:
        """Extract answers from a textbook PDF.

        Args:
            pdf_path: Path to the original textbook PDF.
            subject: Subject name (数据结构/操作系统/etc).
            page_range: Optional (start, end) page range (0-indexed).

        Returns:
            Dict with extraction statistics.
        """
        import fitz

        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if page_range:
            start, end = page_range
        else:
            start, end = 0, total_pages

        logger.info(
            f"Answer extraction: {path.name}, pages {start+1}-{end}/{total_pages}"
        )

        stats = {"pages_processed": 0, "answers_found": 0, "answers_matched": 0, "errors": 0}

        try:
            for page_num in range(start, min(end, total_pages)):
                try:
                    # Render page to image
                    img_path = self.llm.pdf_page_to_image(pdf_path, page_num)

                    # Send to LLM for extraction
                    result_text = self.llm.analyze_page_image(img_path)

                    # Parse the JSON response
                    questions = self._parse_vision_response(result_text)

                    # Match and update answers
                    for q_data in questions:
                        if q_data.get("answer"):
                            matched = self._match_and_update(
                                subject, q_data
                            )
                            stats["answers_found"] += 1
                            if matched:
                                stats["answers_matched"] += 1

                    stats["pages_processed"] += 1
                    logger.info(
                        f"Page {page_num + 1}: found {len(questions)} questions, "
                        f"matched {sum(1 for q in questions if q.get('answer'))}"
                    )

                except Exception as e:
                    logger.error(f"Error processing page {page_num + 1}: {e}")
                    stats["errors"] += 1

        finally:
            doc.close()

        self.db.commit()
        logger.info(f"Extraction complete: {stats}")
        return stats

    def _parse_vision_response(self, text: str) -> list[dict]:
        """Parse the LLM vision response into question dicts."""
        # Try to extract JSON from the response
        text = text.strip()

        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
            return data.get("questions", [])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse vision response as JSON")
            return []

    def _match_and_update(self, subject: str, q_data: dict) -> bool:
        """Try to match an extracted answer to a question in the database.

        Uses fuzzy text matching since OCR text may differ slightly
        from the question bank text.
        """
        q_text = q_data.get("text", "").strip()
        answer = q_data.get("answer", "").strip().upper()
        analysis = q_data.get("analysis", "").strip()

        if not q_text or not answer:
            return False

        # Search for matching question by subject + text similarity
        candidates = self.repo.search(
            subject=subject,
            skip=0,
            limit=500,
        )

        best_match = None
        best_score = 0

        for q in candidates:
            score = self._text_similarity(q.question_text, q_text)
            if score > best_score and score > 0.6:
                best_score = score
                best_match = q

        if best_match and not best_match.answer:
            best_match.answer = answer
            if analysis and not best_match.analysis:
                best_match.analysis = analysis
            logger.debug(
                f"Matched Q#{best_match.id} (score={best_score:.2f}): answer={answer}"
            )
            return True

        return False

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Simple character-level Jaccard similarity for fuzzy matching."""
        if not a or not b:
            return 0.0
        # Normalize: remove whitespace and punctuation
        a_clean = re.sub(r"\s+", "", a)
        b_clean = re.sub(r"\s+", "", b)
        # Compare first 50 chars for efficiency
        a_set = set(a_clean[:50])
        b_set = set(b_clean[:50])
        intersection = a_set & b_set
        union = a_set | b_set
        return len(intersection) / len(union) if union else 0.0
