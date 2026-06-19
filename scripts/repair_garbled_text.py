"""One-time script to repair PUA-garbled text in the question database."""

import argparse
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database.session import SessionLocal
from app.services.garbled_text_repair import GarbledTextRepairService


def main():
    parser = argparse.ArgumentParser(description="Repair PUA garbled text in questions DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed without changing DB")
    parser.add_argument("--pdf-dir", default=None, help="Source PDF directory (default: auto-detect)")
    parser.add_argument("--subject", default=None, help="Only repair questions of this subject")
    parser.add_argument("--reset-progress", action="store_true", help="Clear saved progress and start fresh")
    parser.add_argument("--commit", action="store_true", help="Commit changes to DB (default: flush only)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        service = GarbledTextRepairService(db, pdf_dir=args.pdf_dir)

        if args.reset_progress:
            service.reset_progress()

        report = service.repair_all(dry_run=args.dry_run, subject_filter=args.subject)
        print(report.summary())

        if args.commit and not args.dry_run:
            service.commit()
            print("\nChanges committed to database.")
        elif not args.dry_run and report.total_corrected > 0:
            print("\nNote: changes were flushed but NOT committed. "
                  "Re-run with --commit to persist.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
