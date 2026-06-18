"""PDF Parser module — tailored for 王道408题本 PDFs.

Format characteristics (discovered from actual PDF analysis):
- Text-based PDFs with consistent layout
- Structure: 目录 → 第X章 → X.Y小节 → 一、单项选择题（答案见Pxx） → 题目+ABCD
- Answers are NOT in the question book (referenced as "答案见原书Pxx")
- Original textbook PDFs are scanned images (Phase 4: VLM/OCR for answers)
- Math notation: O(n) renders as "O n\n\n" with special chars
- Footer: "公众号：做题本集结地" + "WD·数据结构· X.章节" + "· 第X 页，共Y 页·"
- Exam questions marked with: 【2023 统考真题】

Strategy pattern for future extensibility (VLM fallback in Phase 4).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import fitz  # PyMuPDF

from app.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger("pdf_parser")


# ─────────────────────────────────────────────
# Data class for parsed output
# ─────────────────────────────────────────────

@dataclass
class ParsedQuestion:
    """Unified output from any PDF parsing strategy."""

    question_text: str = ""
    options: dict[str, str] = field(default_factory=dict)
    answer: str = ""
    analysis: str = ""
    knowledge_tag: list[str] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)
    question_number: int | None = None
    section: str = ""           # e.g., "1.1 数据结构的基本概念"
    answer_ref: str = ""        # e.g., "答案见原书P6"
    exam_year: str = ""         # e.g., "2023统考真题"


# ─────────────────────────────────────────────
# Strategy interface
# ─────────────────────────────────────────────

class PDFParserStrategy(Protocol):
    """Protocol that all parsing strategies must implement."""

    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        ...


# ─────────────────────────────────────────────
# Subject inference from path or filename
# ─────────────────────────────────────────────

SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "数据结构": ["数据结构", "data structure"],
    "操作系统": ["操作系统", "operating system"],
    "计算机组成原理": ["组成原理", "计算机组成", "computer organization"],
    "计算机网络": ["计算机网络", "computer network"],
}


def infer_subject(filepath: str) -> str:
    """Infer the exam subject from the file path (checks parent dirs too)."""
    path = Path(filepath)
    search_text = str(path).lower()
    for subject, keywords in SUBJECT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in search_text:
                return subject
    return "未知科目"


# ─────────────────────────────────────────────
# Footer / noise cleanup patterns
# ─────────────────────────────────────────────

# Footer lines to remove from every page
FOOTER_PATTERNS = [
    re.compile(r"公众号[：:]\s*做题本(?:最TOP|集结地)"),  # "公众号：做题本最TOP/集结地"
    re.compile(r"做题本(?:最TOP|集结地)[^\n]*"),            # standalone watermark variants
    re.compile(r"WD[·].+?[·]\s*\d+\..+?"),           # "WD·数据结构· 1.绪论"
    re.compile(r"王道.+?[·].+?[·]\s*\d+\..+?"),       # "王道计组课后选择题·1.概述"
    re.compile(r"王道.+?课后习题[·].+?"),               # "王道操作系统课后习题·1.概述"
    re.compile(r"王道.+?选择篇[·].+?"),                 # "王道计网选择篇·1.计算机网络体系结构"
    re.compile(r"王道\S+[·][^\n]+"),                     # broad fallback: "王道计组课后选择题·1.概述"
    re.compile(r"[·]?\s*第\s*\d+\s*页[，,]\s*共\s*\d+\s*页\s*[·]?"),  # page numbers
    re.compile(r"所有题本[：:]\s*\S+"),                  # "所有题本：https://..."
    re.compile(r"https?://nocode\.host/\S+"),           # promotional URLs
    re.compile(r"//\s*公众号\s*"),                       # watermark in code comments
]


def clean_page_text(text: str) -> str:
    """Remove footer noise and normalize whitespace in a single page's text."""
    for pat in FOOTER_PATTERNS:
        text = pat.sub("", text)
    # Normalize multiple blank lines to at most 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_trailing_noise(text: str) -> str:
    """Apply all watermark patterns and trim trailing noise from a text block."""
    for pat in FOOTER_PATTERNS:
        text = pat.sub("", text)
    # Remove trailing empty lines and whitespace
    text = text.rstrip()
    text = re.sub(r"\n{2,}$", "", text)
    return text.strip()


# ─────────────────────────────────────────────
# Section / chapter heading patterns
# ─────────────────────────────────────────────

# "第1 章" or "第 1 章" (chapter-level, with possible spaces)
CHAPTER_HEADING = re.compile(
    r"(?:^|\n)\s*第\s*(\d{1,2})\s*章\s*\n?\s*(.+)",
)

# "1.1 数据结构的基本概念" (section-level)
SECTION_HEADING = re.compile(
    r"(?:^|\n)\s*(\d{1,2}\.\d{1,2})\s+(.+)",
)

# "一、单项选择题（答案见P4）" or "（答案见原书P6）"
ANSWER_REF_PATTERN = re.compile(
    r"[（(]?\s*(?:答案见|该节答案见|本节答案见)\s*原?书?\s*P\s*(\d+)\s*[)）]?"
)

# Exam year marker: 【2023 统考真题】
EXAM_YEAR_PATTERN = re.compile(
    r"【\s*(\d{4})\s*(?:统考)?真题\s*】"
)


# ─────────────────────────────────────────────
# Question and option patterns
# ─────────────────────────────────────────────

# Question number at the start of a line: "1." "1、" "12."
# Must be followed by non-whitespace content
QUESTION_NUM = re.compile(
    r"(?:^|\n)\s*(\d{1,4})\s*[.、．]\s*(?=\S)(?!\d)",
    re.MULTILINE,
)

# Option on its own line: "A." "A、" "A." at start of line
OPTION_LINE = re.compile(
    r"\n\s*([A-Ea-e])\s*[.、．)\uff0e]\s*",
)

# "一、单项选择题（答案见P4）" — marks start of a question section
QUESTION_SECTION_HEADER = re.compile(
    r"[一二三四五六七八九十]+[、.]\s*(?:单项选择题|选择题|综合题|填空题|判断题)"
    r"[^\n]*"
)


# ─────────────────────────────────────────────
# PyMuPDF Strategy — primary parser
# ─────────────────────────────────────────────

class PyMuPDFStrategy:
    """Parse 王道408题本 PDFs using PyMuPDF text extraction.

    Parsing flow:
    1. Extract text per page, clean footers
    2. Track chapter/section context across pages
    3. Split text into question blocks by question number
    4. For each block: extract question text + options A/B/C/D
    5. Store answer reference, section, exam year as metadata
    """

    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        """Parse a 题本 PDF file and return all questions."""
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Opening PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        subject = infer_subject(pdf_path)

        try:
            # Step 1: Extract and clean text per page
            pages_text: list[str] = []
            for page in doc:
                text = page.get_text("text")
                text = clean_page_text(text)
                pages_text.append(text)

            full_text = "\n".join(pages_text)
            logger.info(f"Extracted {len(full_text)} chars from {len(doc)} pages")

            # Step 2: Parse into structured questions
            questions = self._parse_full_text(full_text, subject)
            logger.info(
                f"Parsed {len(questions)} questions from {pdf_path_obj.name} "
                f"(subject={subject})"
            )
            return questions

        finally:
            doc.close()

    def _parse_full_text(
        self,
        text: str,
        subject: str,
    ) -> list[ParsedQuestion]:
        """Parse the full merged text into questions with section context."""
        questions: list[ParsedQuestion] = []
        current_chapter: str = ""
        current_section: str = ""
        current_answer_ref: str = ""

        # Find all question numbers and split text into blocks
        q_matches = list(QUESTION_NUM.finditer(text))
        if not q_matches:
            logger.warning("No question patterns found")
            return []

        for i, match in enumerate(q_matches):
            q_num = int(match.group(1))
            start = match.start()
            end = q_matches[i + 1].start() if i + 1 < len(q_matches) else len(text)
            block = text[start:end].strip()

            # Update section context from the text BEFORE this question
            context_start = max(0, start - 500)
            context = text[context_start:start]

            # Check for chapter heading (use last match = most recent)
            ch_matches = list(CHAPTER_HEADING.finditer(context))
            if ch_matches:
                ch_match = ch_matches[-1]
                current_chapter = f"第{ch_match.group(1)}章 {ch_match.group(2).strip()}"

            # Check for section heading (use last match = most recent)
            sec_matches = list(SECTION_HEADING.finditer(context))
            if sec_matches:
                sec_match = sec_matches[-1]
                current_section = f"{sec_match.group(1)} {sec_match.group(2).strip()}"

            # Check for answer reference (use last match = most recent)
            ref_matches = list(ANSWER_REF_PATTERN.finditer(context))
            if ref_matches:
                ref_match = ref_matches[-1]
                current_answer_ref = ref_match.group(0).strip()

            # Check for exam year marker within the question block
            exam_match = EXAM_YEAR_PATTERN.search(block)
            exam_year = f"{exam_match.group(1)}统考真题" if exam_match else ""

            # Parse the question block
            q = self._parse_question_block(
                block, q_num, current_section, current_answer_ref, exam_year
            )
            if q and q.question_text.strip():
                questions.append(q)

        return questions

    def _parse_question_block(
        self,
        block: str,
        q_num: int,
        section: str,
        answer_ref: str,
        exam_year: str,
    ) -> ParsedQuestion | None:
        """Parse a single question block into a ParsedQuestion."""
        q = ParsedQuestion(
            question_number=q_num,
            section=section,
            answer_ref=answer_ref,
            exam_year=exam_year,
        )

        # Remove exam year marker from text
        block = EXAM_YEAR_PATTERN.sub("", block).strip()

        # Remove the leading question number
        block = re.sub(
            r"^\s*\d{1,4}\s*[.、．]\s*",
            "",
            block.strip(),
        ).strip()

        # Find options in the block
        option_matches = list(OPTION_LINE.finditer(block))

        if len(option_matches) >= 2:
            # Has options — extract question text (before first option)
            first_opt_pos = option_matches[0].start()
            q.question_text = block[:first_opt_pos].strip()

            # Extract each option's text
            for j, opt_match in enumerate(option_matches):
                letter = opt_match.group(1).upper()
                opt_start = opt_match.end()
                opt_end = (
                    option_matches[j + 1].start()
                    if j + 1 < len(option_matches)
                    else len(block)
                )
                opt_text = block[opt_start:opt_end].strip()
                # Clean trailing noise
                opt_text = _clean_trailing_noise(opt_text)
                q.options[letter] = opt_text
        else:
            # No standard options — store as-is (fill-in/essay question)
            q.question_text = _clean_trailing_noise(block.strip())

        # Build knowledge tags
        tags = []
        if section:
            tags.append(section)
        if exam_year:
            tags.append(exam_year)
        q.knowledge_tag = tags

        return q


# ─────────────────────────────────────────────
# VLM Fallback Strategy (Phase 4 placeholder)
# ─────────────────────────────────────────────

class VLMFallbackStrategy:
    """Placeholder for multimodal VLM-based parsing.

    Will be implemented in Phase 4 to extract answers and
    analysis from scanned original textbook PDFs.
    """

    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        raise NotImplementedError(
            "VLM fallback strategy will be implemented in Phase 4. "
            "Original textbook PDFs are scanned images requiring OCR/VLM."
        )


# ─────────────────────────────────────────────
# Facade: PDFParser
# ─────────────────────────────────────────────

class PDFParser:
    """Facade that auto-selects the best parsing strategy."""

    def __init__(self, strategy: PDFParserStrategy | None = None):
        self.strategy = strategy or PyMuPDFStrategy()

    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        """Parse a PDF file using the configured strategy."""
        logger.info(f"Parsing PDF with {type(self.strategy).__name__}: {pdf_path}")
        return self.strategy.parse(pdf_path)

    def parse_with_text_hash(self, pdf_path: str) -> list[tuple[ParsedQuestion, str]]:
        """Parse and compute SHA256 hash for each question (for deduplication)."""
        questions = self.parse(pdf_path)
        results: list[tuple[ParsedQuestion, str]] = []
        for q in questions:
            hash_input = q.question_text.strip()
            text_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
            results.append((q, text_hash))
        return results
