"""Markdown Parser — parses MinerU-converted markdown files into ParsedQuestion objects.

MinerU markdown format characteristics (from actual sample analysis):
- ## headers for chapters ("## 第1章 ...") and sections ("## X.Y ...")
- Questions numbered: 1., 2., 23. etc. (numbering restarts per section)
- Options: A., B., C., D. — sometimes inline on same line, sometimes on separate lines
- Images: ![](images/hash.jpg) with relative paths
- Math formulas: $...$ and ${...}$ LaTeX syntax (preserved as-is)
- Answer references: （该节答案见书本P15）
- Exam year markers: 【2009统考真题】
- Code snippets: inline (not fenced) on separate lines
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.core.logging_config import get_logger
from app.services.pdf_parser import ParsedQuestion, infer_subject, EXAM_YEAR_PATTERN

logger = get_logger("markdown_parser")


# ─────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────

# "## 第1章 计算机系统概述"
_MD_CHAPTER = re.compile(r"^##\s*第\s*(\d{1,2})\s*章\s*(.*)")

# "## 1.3 计算机的性能指标" or "## 2.3浮点数的表示与运算"
_MD_SECTION = re.compile(r"^##\s*(\d{1,2}\.\d{1,2})\s*(.*)")

# Question number at start of line: "1." "23." "1、"
_QUESTION_START = re.compile(r"^(\d{1,4})\s*[.、．]\s*(?=\S)(?!\d)", re.MULTILINE)

# Inline option labels: "A." "B." etc.
# (?<![0-9A-Fa-f]) — not preceded by hex digit (avoids matching A3H, F8H, 41A4H etc.)
# (?<![A-Za-z0-9_]) — not preceded by ASCII word char (but allows Chinese chars before)
# This correctly handles: "...主机B. 外部设备" (Chinese before B) and "A. option" (start of line)
_OPT_INLINE = re.compile(r"(?<![0-9A-Fa-f])(?<![A-Za-z0-9_])([A-Da-d])\.\s*")

# Option at start of line: "A. ..." "B. ..."
_OPT_LINE = re.compile(r"^\s*([A-Da-d])\s*[.．、)\uff0e]\s*", re.MULTILINE)

# Answer reference in text: （该节答案见书本P15）
_ANSWER_REF = re.compile(
    r"[（(]\s*(?:该节答案见|答案见|本节答案见)\s*(?:原书|书本)?\s*P\s*(\d+)\s*[)）]"
)

# Standalone answer ref line: "（该节答案见书本P66）" — nothing else on the line
_STANDALONE_REF = re.compile(
    r"^\s*[（(]\s*(?:该节答案见|答案见|本节答案见)\s*(?:原书|书本)?\s*P\s*\d+\s*[)）]\s*$"
)

# Image in markdown: ![](images/hash.jpg) or ![alt](images/hash.jpg)
_IMAGE_REF = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

# Roman numeral sub-items: I. II. III. IV. etc. (for detecting multi-part questions)
_ROMAN_ITEM = re.compile(r"(?<!\w)([IVX]+)\s*[.、．]\s*")


class MarkdownParser:
    """Parse MinerU-converted markdown files into structured questions.

    Designed for 王道408题本 markdown output from MinerU pipeline backend.
    Outputs the same ParsedQuestion format as PDFParser strategies.
    """

    def parse(self, md_path: str) -> list[ParsedQuestion]:
        """Parse a markdown file into a list of ParsedQuestion objects.

        Args:
            md_path: Path to the .md file (images should be in a sibling 'images/' dir).

        Returns:
            List of ParsedQuestion with question_text, options, image_paths, etc.
        """
        md_path = Path(md_path)
        if not md_path.exists():
            logger.error(f"Markdown file not found: {md_path}")
            return []

        md_dir = md_path.parent
        subject = infer_subject(str(md_path))

        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read markdown file: {e}")
            return []

        # Fallback: detect subject from markdown content if path-based detection failed
        if subject == "未知科目":
            subject = self._infer_subject_from_content(text)

        logger.info(f"Parsing markdown: {md_path.name} (subject={subject})")

        return self._parse(text, md_dir, subject)

    def _parse(self, text: str, md_dir: Path, subject: str) -> list[ParsedQuestion]:
        """Internal parsing logic — two-pass approach.

        Pass 1: Split by ## headers into sections (chapter + section context).
        Pass 2: Within each section, split by question numbers and extract fields.
        """
        lines = text.split("\n")
        questions: list[ParsedQuestion] = []

        # === Pass 1: Identify sections by ## headers ===
        sections = self._identify_sections(lines)
        logger.info(f"Found {len(sections)} sections")

        # === Pass 2: Parse questions within each section ===
        for section_name, section_text, answer_ref, chapter in sections:
            q_blocks = self._split_question_blocks(section_text)

            for q_num, q_raw_text in q_blocks:
                q_text, options = self._extract_options(q_raw_text)
                image_paths = self._resolve_images(q_raw_text, md_dir)

                # Extract exam year from question text
                exam_year = ""
                ym = EXAM_YEAR_PATTERN.search(q_text)
                if ym:
                    exam_year = f"{ym.group(1)}统考真题"

                # Determine knowledge_tag from section name
                knowledge_tag: list[str] = []
                if section_name:
                    knowledge_tag.append(section_name)

                q = ParsedQuestion(
                    question_text=q_text.strip(),
                    options=options,
                    image_paths=image_paths,
                    question_number=q_num,
                    section=section_name,
                    answer_ref=answer_ref,
                    exam_year=exam_year,
                    knowledge_tag=knowledge_tag,
                    page_number=None,
                )
                questions.append(q)

        logger.info(
            f"Parsed {len(questions)} questions from markdown "
            f"({sum(1 for q in questions if q.options)} with options, "
            f"{sum(1 for q in questions if q.image_paths)} with images)"
        )
        return questions

    # ─────────────────────────────────────────
    # Pass 1: Section identification
    # ─────────────────────────────────────────

    def _identify_sections(
        self, lines: list[str]
    ) -> list[tuple[str, str, str, str]]:
        """Split lines into sections by ## headers.

        Returns:
            List of (section_name, section_text, answer_ref, chapter).
        """
        sections: list[tuple[str, str, str, str]] = []
        current_section = ""
        current_chapter = ""
        current_lines: list[str] = []
        current_answer_ref = ""

        for line in lines:
            stripped = line.strip()

            # --- Header line ---
            if stripped.startswith("##"):
                header_text = stripped[2:].strip()
                # Remove parenthetical answer refs from header for matching
                clean_header = _ANSWER_REF.sub("", header_text).strip()
                clean_header = re.sub(r"[（(][^)）]*[)）]", "", clean_header).strip()

                ch_m = _MD_CHAPTER.match("## " + clean_header)
                sec_m = _MD_SECTION.match("## " + clean_header)

                if ch_m:
                    # Save previous section
                    if current_lines:
                        sections.append((
                            current_section,
                            "\n".join(current_lines),
                            current_answer_ref,
                            current_chapter,
                        ))
                        current_lines = []
                    current_chapter = f"第{ch_m.group(1)}章 {ch_m.group(2)}".strip()
                    current_section = current_chapter
                    current_answer_ref = ""

                elif sec_m:
                    # Save previous section
                    if current_lines:
                        sections.append((
                            current_section,
                            "\n".join(current_lines),
                            current_answer_ref,
                            current_chapter,
                        ))
                        current_lines = []
                    sec_num = sec_m.group(1)
                    sec_name = sec_m.group(2).strip()
                    current_section = f"{sec_num} {sec_name}" if sec_name else sec_num
                    current_answer_ref = ""

                else:
                    # Non-chapter/section header (e.g., "## 目 录", "## （该节答案见书本P15）")
                    # Check if it contains an answer ref
                    ref_m = _ANSWER_REF.search(header_text)
                    if ref_m:
                        current_answer_ref = f"答案见原书P{ref_m.group(1)}"
                    # Don't treat as a section boundary
                    current_lines.append(line)
                continue

            # --- Standalone answer reference line ---
            if _STANDALONE_REF.match(stripped):
                ref_m = _ANSWER_REF.search(stripped)
                if ref_m:
                    current_answer_ref = f"答案见原书P{ref_m.group(1)}"
                continue  # Don't include in section text

            # --- Regular line ---
            current_lines.append(line)

        # Save last section
        if current_lines:
            sections.append((
                current_section,
                "\n".join(current_lines),
                current_answer_ref,
                current_chapter,
            ))

        return sections

    # ─────────────────────────────────────────
    # Pass 2: Question extraction
    # ─────────────────────────────────────────

    def _split_question_blocks(self, text: str) -> list[tuple[int, str]]:
        """Split section text by question numbers.

        Returns:
            List of (question_number, raw_text).
        """
        matches = list(_QUESTION_START.finditer(text))
        if not matches:
            return []

        blocks: list[tuple[int, str]] = []
        for i, m in enumerate(matches):
            q_num = int(m.group(1))
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block_text = text[start:end].strip()
            if block_text:
                blocks.append((q_num, block_text))

        return blocks

    def _extract_options(self, block: str) -> tuple[str, dict[str, str]]:
        """Extract question text and A/B/C/D options from a question block.

        Handles two layout styles:
        - Inline: "...包括( )A. 运算器 B. 控制器 C. 存储器 D. 输入设备"
        - Line-break: "A. option text\\nB. option text\\n..."

        Returns:
            (question_text, options_dict).
        """
        # Find ALL A-D option label positions using inline pattern
        all_opts = list(_OPT_INLINE.finditer(block))

        # Filter: only keep labels that are A, B, C, D (case-insensitive)
        opt_map: dict[str, re.Match] = {}
        for m in all_opts:
            label = m.group(1).upper()
            if label in "ABCD" and label not in opt_map:
                opt_map[label] = m

        # We need at least A to consider it a multiple-choice question
        if "A" not in opt_map:
            # No options found — might be a fill-in or essay question
            return block.strip(), {}

        # Question text = everything before A's start
        a_pos = opt_map["A"].start()
        question_text = block[:a_pos].strip()

        # Extract each option's text
        options: dict[str, str] = {}
        ordered = ["A", "B", "C", "D"]

        for i, label in enumerate(ordered):
            if label not in opt_map:
                continue

            m = opt_map[label]
            text_start = m.end()

            # Find the next option's start position
            next_start = len(block)
            for nlabel in ordered[i + 1:]:
                if nlabel in opt_map:
                    next_start = opt_map[nlabel].start()
                    break

            opt_text = block[text_start:next_start].strip()

            # Clean up trailing image refs that belong to the next question
            # (rare edge case where image appears between options)
            opt_text = opt_text.rstrip()
            options[label] = opt_text

        return question_text, options

    # ─────────────────────────────────────────
    # Image handling
    # ─────────────────────────────────────────

    def _resolve_images(self, text: str, md_dir: Path) -> list[str]:
        """Extract image references from text and convert to absolute paths.

        Args:
            text: Raw question text (may contain ![](images/hash.jpg) refs).
            md_dir: Directory of the markdown file (for resolving relative paths).

        Returns:
            List of absolute image paths that exist on disk.
        """
        images: list[str] = []
        for m in _IMAGE_REF.finditer(text):
            rel_path = m.group(1)
            abs_path = (md_dir / rel_path).resolve()
            if abs_path.exists():
                # Source path for import_service to copy into runtime media;
                # never store this absolute path directly in the database.
                images.append(str(abs_path))
            else:
                logger.warning(f"Image not found: {abs_path}")
        return images

    # ─────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────

    @staticmethod
    def _extract_answer_ref_from_text(text: str) -> str:
        """Extract answer reference from a text string.

        Returns:
            Formatted answer reference (e.g., "答案见原书P15") or empty string.
        """
        m = _ANSWER_REF.search(text)
        if m:
            return f"答案见原书P{m.group(1)}"
        return ""

    @staticmethod
    def _infer_subject_from_content(text: str) -> str:
        """Infer subject from markdown content (chapter headers, TOC entries).

        Checks the first 3000 chars for subject keywords in ## headers
        or table-of-contents entries. Falls back to "未知科目" if nothing found.
        """
        # Only scan the beginning — TOC and first chapters are enough
        head = text[:3000].lower()

        # Subject keywords ordered by specificity (longer patterns first)
        content_keywords = [
            ("计算机组成原理", ["组成原理", "计算机组成", "机组", "数据通路", "流水线", "cache", "高速缓冲"]),
            ("计算机网络", ["计算机网络", "计网", "tcp", "ip协议", "osi", "路由"]),
            ("数据结构", ["数据结构", "二叉树", "链表", "排序算法", "图论", "哈希"]),
            ("操作系统", ["操作系统", "进程管理", "内存管理", "文件系统", "死锁", "调度"]),
        ]

        for subject, keywords in content_keywords:
            for kw in keywords:
                if kw in head:
                    logger.info(
                        f"Content-based subject detection: '{subject}' "
                        f"(matched keyword: '{kw}')"
                    )
                    return subject

        return "未知科目"
