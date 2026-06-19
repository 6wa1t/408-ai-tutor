"""PUA (Private Use Area) character detection for PDF text extraction artifacts.

The WangDao 408 PDFs use custom-encoded fonts where math symbols and special
characters map to the Unicode Private Use Area (U+E000-U+F8FF). PyMuPDF's
get_text("text") returns these raw PUA codepoints when the ToUnicode CMap is
incomplete or broken.
"""

import re

# Full PUA range
PUA_PATTERN = re.compile(r"[\ue000-\uf8ff]")


def contains_pua(text: str) -> bool:
    """Check if text contains any PUA characters."""
    return bool(PUA_PATTERN.search(text))


def find_pua_chars(text: str) -> list[str]:
    """Return all distinct PUA characters found in text."""
    return list(set(PUA_PATTERN.findall(text)))


def count_pua_chars(text: str) -> int:
    """Count total PUA characters in text."""
    return len(PUA_PATTERN.findall(text))


def strip_pua(text: str) -> str:
    """Remove all PUA characters, leaving the text skeleton for matching."""
    return PUA_PATTERN.sub("", text)


def normalize_for_matching(text: str) -> str:
    """Strip PUA chars and collapse whitespace for fingerprint matching.

    Used to match DB questions (which contain PUA garbled chars) to their
    source PDF pages (which also contain the same PUA chars).
    """
    return re.sub(r"\s+", "", strip_pua(text))


def question_fields_have_pua(
    question_text: str,
    option_a: str = "",
    option_b: str = "",
    option_c: str = "",
    option_d: str = "",
) -> bool:
    """Check if any field of a question contains PUA characters."""
    return any(
        contains_pua(f or "")
        for f in [question_text, option_a, option_b, option_c, option_d]
    )
