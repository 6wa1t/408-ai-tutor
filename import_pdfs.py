"""Quick import script — parse all 题本 PDFs and import into the database."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.database.session import create_tables, SessionLocal
from app.services.import_service import ImportService
from app.services.pdf_parser import infer_subject

# One 选择题 version per subject (same content, different layouts — pick A4留白)
PDF_PATHS = [
    r"D:\01.王道课后习题做题本\数据结构\题本\【A4留白】27王道《数据结构》 - 选择部分.pdf",
    r"D:\01.王道课后习题做题本\操作系统\题本\【A4留白】操作系统选择题做题本.pdf",
    r"D:\01.王道课后习题做题本\计算机组成原理\题本\【A4留白】计算机组成原理选择题做题本.pdf",
    r"D:\01.王道课后习题做题本\计算机网络\题本\【A4有留白】王道计算机网络选择题.pdf",
]

# 综合题/解答题 versions
ESSAY_PATHS = [
    r"D:\01.王道课后习题做题本\数据结构\题本\【A4留白】27王道《数据结构》 - 解答题部分.pdf",
    r"D:\01.王道课后习题做题本\操作系统\题本\【A4留白】27王道操作系统综合题做题本.pdf",
    r"D:\01.王道课后习题做题本\计算机组成原理\题本\【A4留白】计算机组成原理综合题做题本.pdf",
    r"D:\01.王道课后习题做题本\计算机网络\题本\【A4留白】计算机网络综合题做题本.pdf",
]


def main():
    # Ensure tables exist
    create_tables()

    db = SessionLocal()
    try:
        service = ImportService(db)

        print("=" * 60)
        print("408考研题库导入")
        print("=" * 60)

        all_pdfs = PDF_PATHS + ESSAY_PATHS

        for pdf_path in all_pdfs:
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
