"""Quick import script — parse 题本 PDFs and import into the database.

Usage:
    python import_pdfs.py --pdf-dir /path/to/pdf/folder
    python import_pdfs.py --pdf-dir /path/to/pdf/folder --essay-only
    python import_pdfs.py --files file1.pdf file2.pdf
"""

import argparse
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.database.session import create_tables, SessionLocal
from app.services.import_service import ImportService
from app.services.pdf_parser import infer_subject

# Subject keywords used to auto-discover PDFs in subdirectories
_SUBJECT_KEYWORDS = {
    "数据结构": ["数据结构"],
    "操作系统": ["操作系统"],
    "计算机组成原理": ["组成原理", "计组"],
    "计算机网络": ["计算机网络", "计网"],
}


def discover_pdfs(pdf_dir: str) -> list[str]:
    """Recursively find all PDF files under the given directory."""
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.exists():
        print(f"[ERROR] Directory not found: {pdf_dir}")
        return []
    return sorted(str(p) for p in pdf_dir.rglob("*.pdf"))


def main():
    parser = argparse.ArgumentParser(description="Import 408 PDF question banks into the database.")
    parser.add_argument("--pdf-dir", type=str, help="Root directory containing PDF files (recursive scan)")
    parser.add_argument("--files", nargs="+", type=str, help="Specific PDF file paths to import")
    parser.add_argument("--essay-only", action="store_true", help="Only import essay/comprehensive questions")
    args = parser.parse_args()

    if args.files:
        pdf_paths = args.files
    elif args.pdf_dir:
        pdf_paths = discover_pdfs(args.pdf_dir)
        if not pdf_paths:
            print("No PDF files found. Use --pdf-dir or --files to specify paths.")
            return
        print(f"Found {len(pdf_paths)} PDF file(s) in {args.pdf_dir}")
    else:
        parser.print_help()
        print("\nPlease specify --pdf-dir or --files.")
        return

    # Ensure tables exist
    create_tables()

    db = SessionLocal()
    try:
        service = ImportService(db)

        print("=" * 60)
        print("408考研题库导入")
        print("=" * 60)

        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            if not os.path.exists(pdf_path):
                print(f"\n[SKIP] Not found: {filename}")
                continue

            subject = infer_subject(pdf_path)
            print(f"\n[IMPORT] {filename}  (subject: {subject})")
            print("-" * 50)

            try:
                result = service.import_pdf(pdf_path)
                print(f"  Found:   {result.total_found}")
                print(f"  Success: {result.success_count}")
                print(f"  Skipped: {result.skipped_count} (duplicates)")
                print(f"  Errors:  {result.error_count}")

                if result.errors:
                    for err in result.errors[:5]:
                        print(f"  ERROR: {err}")
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback
                traceback.print_exc()

        # Print summary
        print("\n" + "=" * 60)
        print("导入完成 — 数据库统计")
        print("=" * 60)

        from app.repositories.question_repo import QuestionRepository
        repo = QuestionRepository(db)

        total = repo.count()
        print(f"\nTotal questions: {total}")

        subjects = repo.count_by_subject()
        for subj, cnt in subjects:
            print(f"  {subj}: {cnt}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
