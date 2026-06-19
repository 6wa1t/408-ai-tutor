"""Extract images from source PDFs and link to questions via text fingerprint matching.

The original ImageExtractionService relied on question numbers in question_text,
but the PDF parser strips them during import. This script uses text fingerprint
matching (same approach as garbled_text_repair) to map questions to PDF pages,
then links images to questions on the same page.

Usage:
    python extract_images.py --pdf-dir /path/to/pdf/folder --dry-run
    python extract_images.py --pdf-dir /path/to/pdf/folder
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import fitz  # PyMuPDF
import sqlite3

DB_PATH = Path(__file__).parent.parent / "data" / "questions.db"
IMAGE_DIR = Path(__file__).parent.parent / "images"

MIN_WIDTH = 200
MIN_HEIGHT = 150
FINGERPRINT_LEN = 40

# Regex to strip PUA chars and whitespace for fingerprint matching
PUA_RE = re.compile(r'[\ue000-\uf8ff]')


def normalize(text: str) -> str:
    """Strip PUA chars and collapse whitespace for fingerprint matching."""
    return re.sub(r'\s+', '', PUA_RE.sub('', text or ''))


def fingerprint(text: str) -> str:
    """First N normalized characters for matching."""
    return normalize(text)[:FINGERPRINT_LEN]


def discover_pdfs(pdf_dir: str) -> list[str]:
    """Walk directory and return sorted list of PDF paths."""
    result = []
    for root, _, files in os.walk(pdf_dir):
        for f in files:
            if f.lower().endswith('.pdf'):
                result.append(os.path.join(root, f))
    result.sort()
    return result


def find_source_pdf(source_name: str, all_pdfs: list[str]) -> str | None:
    """Find the actual PDF file matching the DB source_pdf name."""
    target = source_name.lower()
    for pdf_path in all_pdfs:
        if Path(pdf_path).name.lower() == target:
            return pdf_path
    # Fallback: match by stem
    target_stem = Path(source_name).stem.lower()
    for pdf_path in all_pdfs:
        if Path(pdf_path).stem.lower() == target_stem:
            return pdf_path
    return None


def infer_subject(source_pdf: str) -> str:
    """Infer subject from PDF filename."""
    name = source_pdf.lower()
    if '数据结构' in name:
        return '数据结构'
    elif '操作系统' in name:
        return '操作系统'
    elif '组成原理' in name:
        return '计算机组成原理'
    elif '计算机网络' in name or '计网' in name:
        return '计算机网络'
    return '未知'


def extract_page_images(doc, page_idx: int) -> list[dict]:
    """Extract qualifying images from one page."""
    page = doc[page_idx]
    info_list = page.get_image_info()
    images = []

    # If get_image_info returns xref=None (inline images), use get_images()
    xref_map = {}
    if any(info.get('xref') is None for info in info_list):
        for i, entry in enumerate(page.get_images(full=True)):
            xref_map[i] = entry[0]

    for idx, info in enumerate(info_list):
        w = info.get('width', 0)
        h = info.get('height', 0)
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            continue
        xref = info.get('xref')
        if xref is None:
            xref = xref_map.get(idx, 0)
        if not xref:
            continue
        try:
            img_dict = doc.extract_image(xref)
        except Exception:
            continue
        if not img_dict or not img_dict.get('image'):
            continue
        images.append({
            'page_idx': page_idx,
            'img_idx': idx,
            'xref': xref,
            'width': img_dict.get('width', w),
            'height': img_dict.get('height', h),
            'bbox': info.get('bbox', (0, 0, 0, 0)),
            'data': img_dict['image'],
            'ext': img_dict.get('ext', 'png'),
        })
    return images


def match_questions_to_pages(db_questions: list[dict], page_fingerprints: list[str]) -> dict[int, list[dict]]:
    """Match each question to a page using fingerprint matching.
    Returns {page_idx: [question_dicts]}.
    """
    page_map = defaultdict(list)
    for q in db_questions:
        fp = fingerprint(q['question_text'])
        if not fp or len(fp) < 5:
            continue
        for page_idx, page_fp in enumerate(page_fingerprints):
            if fp in page_fp:
                page_map[page_idx].append(q)
                break
    return dict(page_map)


def process_one_pdf(pdf_path: str, source_name: str, db: sqlite3.Connection,
                    dry_run: bool) -> tuple[int, int]:
    """Process one PDF: match questions, extract images, update DB."""
    subject = infer_subject(source_name)
    source_stem = Path(pdf_path).stem

    # Get DB questions for this source
    cursor = db.execute(
        "SELECT id, question_text, question_type FROM questions WHERE source_pdf = ? ORDER BY id",
        (source_name,)
    )
    db_questions = [{'id': r[0], 'question_text': r[1], 'question_type': r[2]} for r in cursor.fetchall()]
    if not db_questions:
        return 0, 0

    print(f"  {source_name}: {len(db_questions)} questions in DB")

    # Open PDF and extract page fingerprints
    doc = fitz.open(pdf_path)
    try:
        page_fingerprints = []
        for page in doc:
            raw = page.get_text('text')
            page_fingerprints.append(normalize(raw))

        # Match questions to pages
        page_map = match_questions_to_pages(db_questions, page_fingerprints)
        matched_count = sum(len(v) for v in page_map.values())
        print(f"    Matched {matched_count}/{len(db_questions)} questions to {len(page_map)} pages")

        if not page_map:
            return 0, 0

        images_saved = 0
        questions_updated = 0

        # Process each page with matched questions
        for page_idx in sorted(page_map.keys()):
            page_questions = page_map[page_idx]
            page_images = extract_page_images(doc, page_idx)

            if not page_images:
                continue

            # Sort questions by their order in the DB (proxy for position on page)
            page_questions.sort(key=lambda q: q['id'])

            # Match images to questions: each image goes to the nearest question
            # For simplicity, distribute images round-robin or assign all to the
            # first question if there's only one on the page
            for img_idx, img in enumerate(page_images):
                # Assign image to a question
                if len(page_questions) == 1:
                    target_q = page_questions[0]
                else:
                    # Use y-coordinate: find which question the image is closest to
                    # Since we don't have precise question y-coords from DB,
                    # distribute evenly
                    q_idx = min(img_idx, len(page_questions) - 1)
                    target_q = page_questions[q_idx]

                rel_path = f"questions/{subject}/{source_stem}_p{page_idx:03d}_img{img['img_idx']:03d}.{img['ext']}"

                if dry_run:
                    print(f"    [DRY-RUN] Q{target_q['id']} (page {page_idx+1}) -> {rel_path} "
                          f"({img['width']}x{img['height']})")
                    questions_updated += 1
                else:
                    # Save image file
                    abs_path = IMAGE_DIR / rel_path
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_bytes(img['data'])

                    # Update DB
                    db.execute(
                        "UPDATE questions SET image_path = ? WHERE id = ?",
                        (rel_path, target_q['id'])
                    )
                    images_saved += 1
                    questions_updated += 1

        if not dry_run:
            db.commit()

        return images_saved, questions_updated

    finally:
        doc.close()


def main():
    parser = argparse.ArgumentParser(description="Extract images from PDFs (fingerprint matching)")
    parser.add_argument("--pdf-dir", required=True, help="Source PDF directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH))
    all_pdfs = discover_pdfs(args.pdf_dir)

    # Get distinct source_pdf values from DB
    source_names = [r[0] for r in db.execute(
        "SELECT DISTINCT source_pdf FROM questions WHERE source_pdf IS NOT NULL"
    ).fetchall()]

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"{'='*60}")
    print(f"  Image Extraction — Fingerprint Matching  [{mode}]")
    print(f"  PDF dir   : {args.pdf_dir}")
    print(f"  Found PDFs: {len(all_pdfs)}")
    print(f"  DB sources: {len(source_names)}")
    print(f"  Image dir : {IMAGE_DIR}")
    print(f"  Min size  : {MIN_WIDTH}x{MIN_HEIGHT}")
    print(f"{'='*60}\n")

    total_images = 0
    total_updated = 0
    matched_pdfs = 0

    for source_name in source_names:
        pdf_path = find_source_pdf(source_name, all_pdfs)
        if not pdf_path:
            print(f"  SKIP: {source_name} (not found on disk)")
            continue

        matched_pdfs += 1
        imgs, updated = process_one_pdf(pdf_path, source_name, db, args.dry_run)
        total_images += imgs
        total_updated += updated

    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"{'='*60}")
    print(f"  PDFs matched    : {matched_pdfs}")
    print(f"  Images saved    : {total_images}")
    print(f"  Questions updated: {total_updated}")
    print(f"{'='*60}")

    if args.dry_run:
        print(f"\n[DRY-RUN] No changes made. Remove --dry-run to execute.")

    db.close()


if __name__ == "__main__":
    main()
