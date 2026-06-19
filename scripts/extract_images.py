"""One-time script to extract images from source PDFs and link to questions.

Usage:
    python scripts/extract_images.py
    python scripts/extract_images.py --pdf-dir "D:\\01.王道课后习题做题本"
    python scripts/extract_images.py --dry-run
    python scripts/extract_images.py --min-width 300 --min-height 200
"""

import argparse
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database.session import SessionLocal
from app.services.image_extractor import ImageExtractionService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract images from PDFs and link to questions",
    )
    parser.add_argument(
        "--pdf-dir",
        default=None,
        help="Source PDF directory (default: configured pdf_dir in settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan only, don't save images or update the database",
    )
    parser.add_argument(
        "--min-width",
        type=int,
        default=200,
        help="Minimum image width in pixels (default: 200)",
    )
    parser.add_argument(
        "--min-height",
        type=int,
        default=150,
        help="Minimum image height in pixels (default: 150)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        service = ImageExtractionService(db)
        service.MIN_WIDTH = args.min_width
        service.MIN_HEIGHT = args.min_height

        mode = "DRY-RUN" if args.dry_run else "LIVE"
        print("=" * 60)
        print(f"408考研题库 — 图片提取  [{mode}]")
        print(f"  min-width : {service.MIN_WIDTH}")
        print(f"  min-height: {service.MIN_HEIGHT}")
        if args.pdf_dir:
            print(f"  pdf-dir   : {args.pdf_dir}")
        print("=" * 60)

        report = service.extract_all(pdf_dir=args.pdf_dir, dry_run=args.dry_run)

        print()
        print(report.summary())
        if report.errors:
            print("\nErrors:")
            for err in report.errors:
                print(f"  - {err}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
