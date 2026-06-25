"""Helpers for rendering imported question text."""

from __future__ import annotations

import re
from dataclasses import dataclass


_TABLE_RE = re.compile(r"(<table\b.*?</table>)", re.IGNORECASE | re.DOTALL)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_DETAILS_BLOCK_RE = re.compile(r"<details\b[\s\S]*?</details>", re.IGNORECASE)
_BROKEN_FENCE_LANG_RE = re.compile(r"```[A-Za-z0-9_+-]+```([A-Za-z0-9_+-]+)\s*\n")
_NESTED_INLINE_FENCE_RE = re.compile(r"(?<!^)(?<!\n)```[A-Za-z0-9_+-]+\s*\n?", re.MULTILINE)
_ORPHAN_C_STATEMENT_RE = re.compile(
    r"```c\n(?P<code>[\s\S]*?)\n```\s*\n"
    r"(?P<orphan>(?:[ \t]*[A-Za-z_][^\n`]*;\s*\n?)+)"
    r"\s*```",
    re.MULTILINE,
)
_QUESTION_FENCE_RE = re.compile(
    r"```[A-Za-z0-9_+-]*\s*\n+\s*((?:\(\d+\)|（\d+）)[\s\S]*?)\n```",
    re.MULTILINE,
)
_LATEX_ARRAY_BLOCK_RE = re.compile(
    r"\$\$\s*(.*?\\begin\{array\}.*?\\end\{array\}.*?)\s*\$\$",
    re.DOTALL,
)
_INLINE_ASM_LINE_RE = re.compile(r"^`([A-Za-z][A-Za-z0-9_.]*)`\s+(.+)$")
_ALLOWED_TABLE_RE = re.compile(
    r"</?(?:table|thead|tbody|tr|th|td)\b[^>]*>",
    re.IGNORECASE,
)
_UNSAFE_HTML_RE = re.compile(r"<(?!/?(?:table|thead|tbody|tr|th|td)\b)[^>]+>")
_EVENT_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class QuestionTextPart:
    kind: str
    content: str


def strip_markdown_images(text: str | None) -> str:
    """Remove markdown image references that are rendered through assets."""
    if not text:
        return ""
    cleaned = _MARKDOWN_IMAGE_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_question_text(text: str | None) -> list[QuestionTextPart]:
    """Split question text into markdown and safe table HTML chunks."""
    cleaned = normalize_question_markdown(strip_markdown_images(text))
    if not cleaned:
        return []

    parts: list[QuestionTextPart] = []
    for chunk in _TABLE_RE.split(cleaned):
        if not chunk:
            continue
        if _TABLE_RE.fullmatch(chunk):
            table = sanitize_table_html(chunk)
            if table:
                parts.append(QuestionTextPart("table_html", table))
        else:
            markdown = chunk.strip()
            if markdown:
                parts.append(QuestionTextPart("markdown", markdown))
    return parts


def normalize_question_markdown(text: str | None) -> str:
    """Repair common Markdown/OCR artifacts before Streamlit renders them."""
    if not text:
        return ""

    cleaned = _DETAILS_BLOCK_RE.sub("", text)
    cleaned = _BROKEN_FENCE_LANG_RE.sub(r"```\1\n", cleaned)
    cleaned = _remove_duplicate_empty_fences(cleaned)
    cleaned = _normalize_inline_code_fences(cleaned)
    cleaned = _ORPHAN_C_STATEMENT_RE.sub(
        lambda match: (
            "```c\n"
            + match.group("code").rstrip()
            + "\n"
            + match.group("orphan").strip()
            + "\n```"
        ),
        cleaned,
    )
    cleaned = _QUESTION_FENCE_RE.sub(lambda match: match.group(1).strip(), cleaned)
    cleaned = _remove_duplicate_empty_fences(cleaned)
    cleaned = _merge_orphan_code_continuations(cleaned)
    cleaned = _balance_code_fences(cleaned)
    cleaned = _wrap_inline_assembly_lines(cleaned)
    cleaned = _LATEX_ARRAY_BLOCK_RE.sub(
        lambda match: _latex_array_to_html_table(match.group(1)),
        cleaned,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_table_html(html: str) -> str:
    """Keep only simple table markup and remove event handlers."""
    if not html:
        return ""
    if not _ALLOWED_TABLE_RE.search(html):
        return ""
    readable_math = _html_table_latex_to_text(html)
    without_events = _EVENT_ATTR_RE.sub("", readable_math)
    without_unsafe = _UNSAFE_HTML_RE.sub("", without_events)
    return without_unsafe.strip()


def _html_table_latex_to_text(html: str) -> str:
    return re.sub(r"\$(.*?)\$", lambda match: _inline_latex_to_text(match.group(1)), html)


def _inline_latex_to_text(expr: str) -> str:
    text = expr
    replacements = {
        r"\rightarrow": "->",
        r"\leftarrow": "<-",
        r"\times": "*",
        r"\cdot": "*",
        r"\div": "/",
        r"\leq": "<=",
        r"\geq": ">=",
        r"\neq": "!=",
        r"\sim": "~",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\\(?:mathrm|mathord|mathbb|operatorname|mathsf)\s*\{\{?([^{}]+)\}?\}", r"\1", text)
    text = re.sub(r"\\(?:left|right)\s*", "", text)
    text = re.sub(r"\\[A-Za-z]+", "", text)
    text = text.replace("\\", "")
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return text.strip()

def _normalize_inline_code_fences(text: str) -> str:
    lines: list[str] = []
    in_code = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            lines.append(line)
            in_code = not in_code
            continue

        match = re.search(r"```([A-Za-z0-9_+-]*)\s*(.*)$", line)
        if match is None:
            lines.append(line)
            continue

        before = line[: match.start()].rstrip()
        trailing = match.group(2).strip()
        if in_code:
            if before:
                lines.append(before)
            if trailing:
                lines.append(trailing)
            continue

        if before:
            lines.append(before)
        language = match.group(1)
        lines.append("```" + language)
        if trailing:
            lines.append(trailing)
        in_code = True

    return "\n".join(lines)

def _merge_orphan_code_continuations(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    in_code = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                result.append(line)
                i += 1
                continue

            next_index = i + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1

            closing_index = next_index
            continuation: list[str] = []
            while closing_index < len(lines):
                candidate = lines[closing_index]
                if candidate.strip().startswith("```"):
                    break
                continuation.append(candidate)
                closing_index += 1

            if (
                closing_index < len(lines)
                and len(continuation) <= 40
                and _looks_like_code_continuation(continuation)
            ):
                result.extend(continuation)
                i = closing_index
                continue

            in_code = False
            result.append(line)
            i += 1
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _looks_like_code_continuation(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        return False
    first = meaningful[0]
    if first.startswith(("(", "[", "【")):
        return False
    if re.search(r"[\u4e00-\u9fff]", first) and ";" not in first and not first.startswith(("{", "}")):
        return False
    if first.endswith((".", "。", "，", ",")):
        return False
    code_markers = (
        ";",
        "=",
        "for(",
        "for (",
        "while(",
        "while (",
        "if(",
        "if (",
        "{",
        "}",
        "printf(",
        "scanf(",
        "return ",
    )
    if any(re.match(r"^\d+\s+[0-9A-Fa-f]{6,}\b", line) for line in meaningful):
        return True
    return any(any(marker in line for marker in code_markers) for line in meaningful)

def _balance_code_fences(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    in_code = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code and stripped == "```" and not _plain_fence_starts_code(lines, index):
                continue
            in_code = not in_code
            result.append(line)
            continue
        if in_code and stripped.startswith("</details>"):
            result.append("```")
            in_code = False
        result.append(line)

    if in_code:
        result.append("```")
    return "\n".join(result)


def _plain_fence_starts_code(lines: list[str], index: int) -> bool:
    continuation: list[str] = []
    for candidate in lines[index + 1 : index + 8]:
        if candidate.strip().startswith("```"):
            break
        continuation.append(candidate)
    return _looks_like_code_continuation(continuation)

def _remove_duplicate_empty_fences(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    previous_was_fence = False

    for line in lines:
        stripped = line.strip()
        is_plain_fence = stripped == "```"
        if is_plain_fence and previous_was_fence:
            continue
        result.append(line)
        previous_was_fence = is_plain_fence

    return "\n".join(result)


def _wrap_inline_assembly_lines(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    pending: list[str] = []

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        if len(pending) >= 2:
            result.append("```asm")
            result.extend(pending)
            result.append("```")
        else:
            result.append(pending[0])
        pending = []

    for line in lines:
        match = _INLINE_ASM_LINE_RE.match(line.strip())
        if match:
            pending.append(f"{match.group(1)} {match.group(2)}")
            continue
        flush_pending()
        result.append(line)

    flush_pending()
    return "\n".join(result)


def _latex_array_to_html_table(block: str) -> str:
    body_match = re.search(
        r"\\begin\{array\}\s*\{[^}]*\}(.*?)\\end\{array\}",
        block,
        re.DOTALL,
    )
    if body_match is None:
        return ""

    rows = []
    for raw_row in re.split(r"\\\\", body_match.group(1)):
        cells = [_latex_cell_to_text(cell) for cell in raw_row.split("&")]
        cells = [cell for cell in cells if cell]
        if cells:
            row_html = "".join(f"<td>{_escape_html(cell)}</td>" for cell in cells)
            rows.append(f"<tr>{row_html}</tr>")

    if not rows:
        return ""
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def _latex_cell_to_text(cell: str) -> str:
    text = cell
    text = re.sub(r"\\(?:mathrm|mathord|mathbb|operatorname|mathsf)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:cal)\s*\{([^{}]*)\}", r"\1", text)
    replacements = {
        r"\qquad": " ",
        r"\cdots": "...",
        r"\lambda": "lambda",
        r"\Lambda": "Lambda",
        r"\partial": "partial",
        r"\sim": "~",
        r"\ast": "*",
        r"\flat": "b",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = text.replace("\\", " ")
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;")


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )










