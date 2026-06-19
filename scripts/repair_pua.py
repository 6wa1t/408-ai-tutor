"""
PUA Garbled Text Repair — Static Mapping Table Approach
========================================================
Repairs 267 questions with PMExtra font PUA characters (U+F0xx)
by replacing them with correct Unicode math symbols.

Usage:
    python repair_pua.py              # Execute repair
    python repair_pua.py --dry-run    # Preview only, no DB changes
"""

import sqlite3
import sys
import re
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "questions.db"

# ─── Paired bracket/paren characters ───────────────────────
# These always appear in pairs (opening + closing) with
# optional whitespace/newlines between them.
PAIRED_REPLACEMENTS = [
    # (pua_char, opening_replacement, closing_replacement)
    ('\uf0ee', '(', ')'),   # Parentheses: O(n²), T(n), etc.
    ('\uf0f6', '[', ']'),   # Square brackets: A[0..n]
    ('\uf0f4', '|', '|'),   # Absolute value: |V| > |E|
    ('\uf0f7', '\u230a', '\u230b'),  # Floor brackets: ⌊x⌋
    ('\uf0f8', '\u2308', '\u2309'),  # Ceiling brackets: ⌈x⌉
]

# ─── Single-char replacements ──────────────────────────────
# These PUA chars map to specific Unicode symbols based on
# PMExtra/Symbol font encoding + context analysis.
SINGLE_REPLACEMENTS = {
    # Graph tuple notation: ⟨V, E⟩ — the triple F0E0+F0E1+F0E2 appears
    # as a separate line in vertical text layout, acting as redundant bracket
    # decoration around tuple data that's already present. Remove entirely.
    '\uf0e0': '',          # remove (left angle bracket, redundant)
    '\uf0e1': '',          # remove (separator, redundant)
    '\uf0e2': '',          # remove (right angle bracket, redundant)

    # Prime/accent: T', V', E'
    '\uf00a': "'",          # '  (prime mark)

    # Matrix/large bracket pieces (vertical layout)
    '\uf0e8': '\u23a7',     # ⎧  LEFT CURLY BRACKET UPPER CORNER
    '\uf0e9': '\u23ab',     # ⎫  RIGHT CURLY BRACKET UPPER CORNER
    '\uf0ea': '\u23aa',     # ⎪  CURLY BRACKET EXTENSION

    # Piecewise brace
    '\uf0e3': '\u23a7',     # ⎧  (left curly bracket upper corner)

    # Set union / composition
    '\uf0e4': '\u222a',     # ∪  UNION

    # Summation
    '\uf0b1': '\u2211',     # ∑  N-ARY SUMMATION

    # Overline (boolean complement): SF̄ + OF = 1
    '\uf0dc': '\u0305',     # ̅   COMBINING OVERLINE

    # Underbrace annotations
    '\uf0fb': '\u23df',     # ⏟  CURLY BRACKET (used as underbrace)
    '\uf0fc': '\u23df',     # ⏟
    '\uf0fd': '\u23df',     # ⏟
}

FIELDS = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'analysis']


def repair_paired(text: str, pua_ch: str, open_ch: str, close_ch: str) -> str:
    """Replace paired PUA brackets with opening + closing chars.

    Handles patterns like:
        F0EE\\n...\\nF0EE  →  (...)
    Collapses all whitespace/newlines between the pair.
    """
    # Pattern: pua_char + any whitespace/newlines + pua_char → collapsed
    pattern = re.escape(pua_ch) + r'\s+' + re.escape(pua_ch)
    text = re.sub(pattern, open_ch + close_ch, text)

    # Any remaining lone pua chars → opening bracket
    text = text.replace(pua_ch, open_ch)
    return text


def repair_single(text: str, mapping: dict) -> str:
    """Replace individual PUA chars using the mapping table."""
    for pua_ch, replacement in mapping.items():
        text = text.replace(pua_ch, replacement)
    return text


def repair_text(text: str) -> str:
    """Apply all PUA repairs to a text string."""
    if not text:
        return text

    # Step 1: Fix paired brackets first (before single-char replacements)
    for pua_ch, open_ch, close_ch in PAIRED_REPLACEMENTS:
        text = repair_paired(text, pua_ch, open_ch, close_ch)

    # Step 2: Fix single-char replacements
    text = repair_single(text, SINGLE_REPLACEMENTS)

    return text


def has_pua(text: str) -> bool:
    """Check if text contains any PUA characters."""
    if not text:
        return False
    return bool(re.search(r'[\ue000-\uf8ff]', text))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    dry_run = '--dry-run' in sys.argv

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Find affected questions
    affected_ids = []
    rows = cursor.execute(
        f"SELECT id, {', '.join(FIELDS)} FROM questions"
    ).fetchall()

    for row in rows:
        for field in FIELDS:
            if has_pua(row[field]):
                affected_ids.append(row['id'])
                break

    print(f"Found {len(affected_ids)} questions with PUA characters")

    if dry_run:
        print("\n─── DRY RUN ───")
        # Show samples for each PUA char
        from collections import Counter
        pua_counter = Counter()

        for row in rows:
            for field in FIELDS:
                text = row[field]
                if text:
                    for ch in text:
                        if '\ue000' <= ch <= '\uf8ff':
                            pua_counter[ch] += 1

        print(f"Unique PUA chars: {len(pua_counter)}")
        print(f"Total occurrences: {sum(pua_counter.values())}")
        print("\nCharacters to replace:")
        for ch, cnt in pua_counter.most_common():
            cp = ord(ch)
            replacement = "?"
            for p, o, c in PAIRED_REPLACEMENTS:
                if p == ch:
                    replacement = f"{o}...{c} (paired)"
                    break
            if ch in SINGLE_REPLACEMENTS:
                r = SINGLE_REPLACEMENTS[ch]
                replacement = f"{r} (U+{ord(r):04X})"
            print(f"  U+{cp:04X} ({cnt:5d}x) → {replacement}")

        # Show a few before/after samples
        print("\n─── Sample Before/After ───")
        sample_ids = affected_ids[:5]
        for qid in sample_ids:
            row = cursor.execute(
                f"SELECT subject, {', '.join(FIELDS)} FROM questions WHERE id=?",
                (qid,)
            ).fetchone()
            print(f"\n  Question #{qid} ({row['subject']}):")
            for field in FIELDS[:3]:  # Only show first 3 fields for brevity
                text = row[field]
                if text and has_pua(text):
                    before = text[:80].replace('\n', ' ')
                    after = repair_text(text)[:80].replace('\n', ' ')
                    print(f"    {field}:")
                    print(f"      BEFORE: {before}")
                    print(f"      AFTER:  {after}")

        print(f"\n[DRY-RUN] Would repair {len(affected_ids)} questions. "
              f"Run without --dry-run to apply.")
        conn.close()
        return

    # ── Execute repair ──
    print("\n─── Executing Repair ───")
    repaired = 0
    total_pua_before = 0
    total_pua_after = 0

    for qid in affected_ids:
        row = cursor.execute(
            f"SELECT {', '.join(FIELDS)} FROM questions WHERE id=?",
            (qid,)
        ).fetchone()

        updates = {}
        q_pua_before = 0
        q_pua_after = 0

        for field in FIELDS:
            text = row[field]
            if text and has_pua(text):
                q_pua_before += sum(1 for ch in text if '\ue000' <= ch <= '\uf8ff')
                fixed = repair_text(text)
                q_pua_after += sum(1 for ch in fixed if '\ue000' <= ch <= '\uf8ff')
                updates[field] = fixed

        if updates:
            set_clause = ', '.join(f"{f} = ?" for f in updates)
            values = list(updates.values()) + [qid]
            cursor.execute(
                f"UPDATE questions SET {set_clause} WHERE id = ?",
                values
            )
            repaired += 1
            total_pua_before += q_pua_before
            total_pua_after += q_pua_after

    conn.commit()

    # ── Verification ──
    remaining = cursor.execute(
        f"SELECT COUNT(*) FROM questions WHERE " +
        " OR ".join(f"{f} GLOB '*[\ue000-\uf8ff]*'" for f in FIELDS)
    ).fetchone()[0]

    print(f"\n{'='*50}")
    print(f"  PUA Garbled Text Repair Complete")
    print(f"{'='*50}")
    print(f"  Questions repaired     : {repaired}")
    print(f"  PUA chars before       : {total_pua_before}")
    print(f"  PUA chars remaining    : {total_pua_after}")
    print(f"  Questions still broken : {remaining}")
    print(f"{'='*50}")

    # Show a few after-samples
    print("\n─── Verification Samples ───")
    for qid in affected_ids[:5]:
        row = cursor.execute(
            f"SELECT subject, question_text, option_a FROM questions WHERE id=?",
            (qid,)
        ).fetchone()
        print(f"\n  Q#{qid} ({row['subject']}):")
        for f in ['question_text', 'option_a']:
            text = row[f]
            if text:
                preview = text[:100].replace('\n', ' ')
                print(f"    {f}: {preview}")

    conn.close()


if __name__ == '__main__':
    main()
