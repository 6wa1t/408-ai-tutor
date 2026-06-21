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
    page_number: int | None = None  # 0-indexed page in source PDF


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

    def parse(self, pdf_path: str, extract_images: bool = False) -> list[ParsedQuestion]:
        """Parse a 题本 PDF file and return all questions.

        Args:
            pdf_path: Path to the PDF file.
            extract_images: If True, also extract embedded images and attach
                their file paths to the corresponding ParsedQuestion objects.
        """
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Opening PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        subject = infer_subject(pdf_path)

        try:
            # Step 1: Extract and clean text per page, build offset map
            pages_text: list[str] = []
            page_offsets: list[tuple[int, int, int]] = []  # (start, end, page_idx)
            offset = 0
            for page_idx, page in enumerate(doc):
                text = page.get_text("text")
                text = clean_page_text(text)
                pages_text.append(text)
                end = offset + len(text)
                page_offsets.append((offset, end, page_idx))
                offset = end + 1  # +1 for the \n joiner

            full_text = "\n".join(pages_text)
            logger.info(f"Extracted {len(full_text)} chars from {len(doc)} pages")

            # Step 2: Parse into structured questions with page tracking
            questions = self._parse_full_text(full_text, subject, page_offsets)

            # Step 3: PUA detection warning
            from app.services.pua_detector import contains_pua
            pua_count = sum(
                1 for q in questions
                if contains_pua(q.question_text) or any(contains_pua(v) for v in q.options.values())
            )
            if pua_count > 0:
                logger.warning(
                    f"PUA characters detected in {pua_count}/{len(questions)} questions. "
                    f"Run scripts/repair_garbled_text.py to fix."
                )

            # Step 4: Extract embedded images if requested
            if extract_images:
                self._extract_and_attach_images(doc, questions, subject, pdf_path_obj.stem)

            logger.info(
                f"Parsed {len(questions)} questions from {pdf_path_obj.name} "
                f"(subject={subject})"
            )
            return questions

        finally:
            doc.close()

    @staticmethod
    def _find_page(char_offset: int, page_offsets: list[tuple[int, int, int]]) -> int:
        """Binary search for the page that contains the given character offset."""
        lo, hi = 0, len(page_offsets) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end, _ = page_offsets[mid]
            if char_offset < start:
                hi = mid - 1
            elif char_offset >= end:
                lo = mid + 1
            else:
                return page_offsets[mid][2]
        return page_offsets[-1][2] if page_offsets else 0

    def _parse_full_text(
        self,
        text: str,
        subject: str,
        page_offsets: list[tuple[int, int, int]] | None = None,
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
                if page_offsets:
                    q.page_number = self._find_page(start, page_offsets)
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

    def _extract_and_attach_images(
        self,
        doc: fitz.Document,
        questions: list[ParsedQuestion],
        subject: str,
        source_stem: str,
    ) -> None:
        """Extract embedded images from PDF and attach paths to questions.

        Uses the ImageExtractionService's matching logic internally but
        operates on in-memory ParsedQuestion objects rather than DB records.
        """
        from app.config import get_settings

        settings = get_settings()
        image_dir = Path(settings.image_dir)
        min_width, min_height = 200, 150

        # Build question-number → ParsedQuestion mapping
        q_by_num: dict[int, list[ParsedQuestion]] = {}
        for q in questions:
            if q.question_number is not None:
                q_by_num.setdefault(q.question_number, []).append(q)

        for page_idx in range(len(doc)):
            page = doc[page_idx]

            # Get question positions on this page
            q_positions = self._get_question_y_positions(page)
            # q_positions: list[(question_number, y_top)]

            # Extract qualifying images
            for img_idx, info in enumerate(page.get_image_info()):
                xref = info.get("xref", 0)
                width = info.get("width", 0)
                height = info.get("height", 0)
                bbox = info.get("bbox", (0, 0, 0, 0))

                if width < min_width or height < min_height:
                    continue

                img_y = bbox[1]  # top y-coordinate

                # Find closest question above this image
                matched_q_num: int | None = None
                best_distance = float("inf")
                for q_num, q_y in q_positions:
                    if q_y <= img_y:
                        distance = img_y - q_y
                        if distance < best_distance:
                            best_distance = distance
                            matched_q_num = q_num

                if matched_q_num is None:
                    continue

                # Attach image path to matched questions
                matched_qs = q_by_num.get(matched_q_num, [])
                ext = "jpeg"
                if xref > 0:
                    try:
                        img_data = doc.extract_image(xref)
                        ext = img_data.get("ext", "jpeg")
                    except Exception:
                        pass

                img_filename = f"{source_stem}_p{page_idx:03d}_img{img_idx:03d}.{ext}"
                rel_path = str(Path("questions") / subject / img_filename)

                for q in matched_qs:
                    if q.page_number is not None and q.page_number != page_idx:
                        continue  # Skip if question is on a different page
                    if rel_path not in q.image_paths:
                        q.image_paths.append(rel_path)

        # Count questions with images
        img_count = sum(1 for q in questions if q.image_paths)
        if img_count > 0:
            logger.info(f"Attached images to {img_count} questions")

    @staticmethod
    def _get_question_y_positions(page: fitz.Page) -> list[tuple[int, float]]:
        """Detect question numbers and their y-coordinates on a page.

        Returns list of (question_number, y_top) sorted by y_top.
        """
        positions: list[tuple[int, float]] = []
        text_dict = page.get_text("dict")
        q_line_re = re.compile(r"^\s*(\d{1,4})\s*[.、．]\s*\S")

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = "".join(
                    span.get("text", "") for span in line.get("spans", [])
                )
                m = q_line_re.match(line_text)
                if m:
                    q_num = int(m.group(1))
                    y_top = line["bbox"][1]
                    positions.append((q_num, y_top))

        positions.sort(key=lambda t: t[1])
        return positions


# ─────────────────────────────────────────────
# VLM Fallback Strategy (Phase 4 placeholder)
# ─────────────────────────────────────────────

class VLMFallbackStrategy:
    """VLM-based parsing for scanned/image PDFs.

    Renders each page to an image, sends to vision LLM for structured
    extraction of questions, options, chapter/section context, and metadata.

    Use when PyMuPDFStrategy returns 0 questions (scanned PDFs).
    """

    def __init__(self, llm_service=None):
        """Initialize with optional pre-configured LLM service.

        Args:
            llm_service: An LLMService instance. If None, uses the global singleton.
        """
        self._llm = llm_service

    @property
    def llm(self):
        if self._llm is None:
            from app.services.llm_service import get_llm_service
            self._llm = get_llm_service()
        return self._llm

    def parse(
        self,
        pdf_path: str,
        page_range: tuple[int, int] | None = None,
    ) -> list[ParsedQuestion]:
        """Parse a scanned PDF using vision LLM.

        Args:
            pdf_path: Path to the PDF file.
            page_range: Optional (start, end) 0-indexed page range.
                        If None, processes all pages.

        Returns:
            List of ParsedQuestion objects.
        """
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Fail fast if vision API is not configured
        if not self.llm.is_vision_configured():
            raise RuntimeError(
                "视觉模型未配置。扫描PDF需要视觉API支持。"
                "请在 .env 中设置 VISION_API_KEY（通义千问VL）。"
                "详见 .env.example 中的说明。"
            )

        logger.info(f"VLM fallback: opening PDF {pdf_path}")
        doc = fitz.open(pdf_path)
        subject = infer_subject(pdf_path)
        pdf_stem = pdf_path_obj.stem
        settings = get_settings()
        image_dir = Path(settings.image_dir)
        total_pages = len(doc)

        if page_range:
            start, end = page_range
        else:
            start, end = 0, total_pages
        end = min(end, total_pages)

        questions: list[ParsedQuestion] = []
        # Track chapter/section context across pages
        context: dict[str, str] = {"chapter": "", "section": ""}

        try:
            for page_idx in range(start, end):
                try:
                    # ── 1. 渲染页面为高分辨率图片 ──
                    pix = None
                    try:
                        page = doc[page_idx]
                        pix = page.get_pixmap(dpi=200)
                        page_img_path = str(
                            image_dir / f"{pdf_stem}_page{page_idx + 1}.png"
                        )
                        pix.save(page_img_path)
                    except Exception as e:
                        logger.error(
                            f"Failed to render page {page_idx + 1}: {e}"
                        )
                        continue

                    # ── 2. 发送VLM提取题目 + 配图位置 ──
                    result = self.llm.analyze_questions_page(
                        page_img_path, context
                    )

                    # Update context from VLM response
                    page_context = result.get("context", {})
                    if page_context.get("chapter"):
                        context["chapter"] = page_context["chapter"]
                    if page_context.get("section"):
                        context["section"] = page_context["section"]

                    # ── 3. 按VLM返回的位置裁剪配图 ──
                    # 批处理：先收集所有需要裁剪的图片
                    img_attachments: dict[int, list[str]] = {}
                    for q_data in result.get("questions", []):
                        q_num = q_data.get("number")
                        if q_num is None:
                            continue
                        y_range = q_data.get("image_y_range")
                        if (
                            y_range
                            and isinstance(y_range, (list, tuple))
                            and len(y_range) >= 2
                        ):
                            y1_ratio = max(0.0, min(1.0, float(y_range[0])))
                            y2_ratio = max(0.0, min(1.0, float(y_range[1])))
                            # 过滤高度太小的误报
                            if y2_ratio - y1_ratio > 0.02:
                                y1 = int(y1_ratio * pix.height)
                                y2 = int(y2_ratio * pix.height)
                                x1 = int(0.05 * pix.width)
                                x2 = int(0.95 * pix.width)
                                clip_rect = fitz.Rect(x1, y1, x2, y2)
                                img_pix = fitz.Pixmap(pix, clip_rect)

                                img_filename = (
                                    f"{pdf_stem}_p{page_idx:03d}"
                                    f"_q{q_num:03d}_vlm.png"
                                )
                                rel_path = str(
                                    Path("questions") / subject / img_filename
                                )
                                abs_path = image_dir / rel_path
                                abs_path.parent.mkdir(parents=True, exist_ok=True)
                                img_pix.save(str(abs_path))
                                img_attachments.setdefault(q_num, []).append(rel_path)

                    # ── 4. 构建ParsedQuestion对象 ──
                    for q_data in result.get("questions", []):
                        q = self._build_parsed_question(
                            q_data, context, page_idx, subject, img_attachments
                        )
                        if q and q.question_text.strip():
                            questions.append(q)

                    # Clean up rendered full-page image
                    try:
                        Path(page_img_path).unlink(missing_ok=True)
                    except OSError:
                        pass

                    # Progress logging
                    if (page_idx - start + 1) % 5 == 0 or page_idx == end - 1:
                        logger.info(
                            f"VLM progress: page {page_idx + 1}/{end} "
                            f"({len(questions)} questions so far)"
                        )

                except Exception as e:
                    logger.error(
                        f"VLM error on page {page_idx + 1}: {e}"
                    )
                    # Continue with next page
                    continue

        finally:
            doc.close()

        logger.info(
            f"VLM fallback complete: {len(questions)} questions from "
            f"{end - start} pages of {pdf_path_obj.name} "
            f"(subject={subject})"
        )
        img_count = sum(1 for q in questions if q.image_paths)
        if img_count:
            logger.info(
                f"VLM cropped diagram images for {img_count} questions"
            )
        return questions

    @staticmethod
    def _build_parsed_question(
        q_data: dict,
        context: dict[str, str],
        page_idx: int,
        subject: str,
        img_attachments: dict[int, list[str]] | None = None,
    ) -> ParsedQuestion | None:
        """Convert a VLM response dict into a ParsedQuestion.

        Args:
            q_data: Question data from VLM response.
            context: Chapter/section context from VLM.
            page_idx: 0-indexed page number.
            subject: Inferred subject name.
            img_attachments: Dict mapping question_number → [rel_path, ...]
                             of cropped diagram images from this page.

        Returns:
            ParsedQuestion or None if question text is empty.
        """
        text = str(q_data.get("text", "")).strip()
        if not text:
            return None

        q_num = q_data.get("number")
        q = ParsedQuestion(
            question_number=q_num,
            question_text=text,
            page_number=page_idx,
        )

        # Options
        options = q_data.get("options", {})
        if isinstance(options, dict):
            for letter in ("A", "B", "C", "D", "E"):
                if letter in options and options[letter]:
                    q.options[letter] = str(options[letter]).strip()

        # Answer and analysis
        q.answer = str(q_data.get("answer", "")).strip().upper()
        q.analysis = str(q_data.get("analysis", "")).strip()

        # Exam year
        q.exam_year = str(q_data.get("exam_year", "")).strip()

        # Build section from context
        section = context.get("section", "")
        chapter = context.get("chapter", "")
        if section:
            q.section = section
        elif chapter:
            q.section = chapter

        # Build knowledge tags
        tags = []
        if section:
            tags.append(section)
        elif chapter:
            tags.append(chapter)
        if q.exam_year:
            tags.append(q.exam_year)
        q.knowledge_tag = tags

        # Attach cropped diagram images
        if img_attachments and q_num is not None:
            paths = img_attachments.get(q_num)
            if paths:
                q.image_paths = paths

        return q


# ─────────────────────────────────────────────
# Facade: PDFParser
# ─────────────────────────────────────────────

class PDFParser:
    """Facade that auto-selects the best parsing strategy.

    Auto-detection flow:
    1. Quick scan: check if PDF is scanned (pages have little/no text)
       → Scanned: directly use VLMFallbackStrategy (vision-based)
    2. Not scanned: use PyMuPDFStrategy (fast, text-based)
    3. If PyMuPDF finds 0 questions → fallback to VLM

    Set force_vlm=True to skip detection and go directly to VLM.
    """

    # Scanned PDF detection: if >_SCAN_THRESHOLD of pages have
    # fewer than _MIN_TEXT_CHARS characters, treat as scanned.
    _SCAN_THRESHOLD = 0.5   # 50%+ pages
    _MIN_TEXT_CHARS = 30    # fewer than 30 chars = "blank page"

    def __init__(
        self,
        strategy: PDFParserStrategy | None = None,
        force_vlm: bool = False,
    ):
        self._explicit_strategy = strategy
        self._force_vlm = force_vlm
        self._used_vlm = False  # Track whether VLM was used in last parse

    @property
    def strategy(self) -> PDFParserStrategy:
        return self._explicit_strategy or PyMuPDFStrategy()

    @property
    def used_vlm(self) -> bool:
        """True if the last parse() call used VLM fallback."""
        return self._used_vlm

    # ── 扫描PDF快速检测 ────────────────────────

    @staticmethod
    def _quick_scanned_check(pdf_path: str) -> bool:
        """快速检测PDF是否为扫描版（图片型）。

        打开PDF，逐页提取文本。如果大多数页面文本极少，
        说明是扫描版PDF，需要走VLM路线。
        """
        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return False

        try:
            total_pages = len(doc)
            if total_pages == 0:
                return False

            blank_count = 0
            for page in doc:
                text = page.get_text("text").strip()
                if len(text) < PDFParser._MIN_TEXT_CHARS:
                    blank_count += 1

            ratio = blank_count / total_pages
            logger.info(
                f"Scanned PDF check: {pdf_path} → "
                f"{blank_count}/{total_pages} pages near-empty "
                f"({ratio:.0%}), threshold={PDFParser._SCAN_THRESHOLD:.0%}"
            )
            return ratio >= PDFParser._SCAN_THRESHOLD

        finally:
            doc.close()

    # ── 主解析入口 ─────────────────────────────

    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        """Parse a PDF file with auto-detect and fallback.

        Detection flow:
        - If force_vlm → VLM directly
        - If explicit strategy → use it directly
        - If quick scan detects scanned PDF → VLM
        - Otherwise → PyMuPDF text extraction
        - If PyMuPDF returns 0 questions → VLM fallback

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of ParsedQuestion objects.
        """
        self._used_vlm = False

        # ── 1. 强制VLM模式 ──
        if self._force_vlm:
            logger.info(f"Force VLM mode for: {pdf_path}")
            vlm = VLMFallbackStrategy()
            self._used_vlm = True
            return vlm.parse(pdf_path)

        # ── 2. 显式指定策略 ──
        if self._explicit_strategy is not None:
            logger.info(
                f"Parsing PDF with {type(self._explicit_strategy).__name__}: {pdf_path}"
            )
            return self._explicit_strategy.parse(pdf_path)

        # ── 3. 扫描PDF检测 ──
        if self._quick_scanned_check(pdf_path):
            logger.info(
                f"Detected scanned PDF: {pdf_path}. "
                f"Routing to VLM vision-based extraction."
            )
            vlm = VLMFallbackStrategy()
            self._used_vlm = True
            return vlm.parse(pdf_path)

        # ── 4. 文字型PDF：PyMuPDF提取 ──
        text_strategy = PyMuPDFStrategy()
        logger.info(f"Parsing text PDF with PyMuPDFStrategy: {pdf_path}")
        results = text_strategy.parse(pdf_path)

        if results:
            logger.info(f"PyMuPDF extracted {len(results)} questions")
            return results

        # ── 5. PyMuPDF未找到任何题目 → VLM降级 ──
        logger.warning(
            f"PyMuPDF extracted 0 questions from {pdf_path}. "
            f"Auto-fallback to VLM (vision-based extraction). "
            f"This will make API calls for each page."
        )
        vlm = VLMFallbackStrategy()
        self._used_vlm = True
        return vlm.parse(pdf_path)

    def parse_with_text_hash(self, pdf_path: str) -> list[tuple[ParsedQuestion, str]]:
        """Parse and compute SHA256 hash for each question (for deduplication)."""
        questions = self.parse(pdf_path)
        results: list[tuple[ParsedQuestion, str]] = []
        for q in questions:
            hash_input = q.question_text.strip()
            text_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
            results.append((q, text_hash))
        return results
