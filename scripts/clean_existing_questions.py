#!/usr/bin/env python3
"""一次性脚本：清洗数据库中所有题目的文本格式。

对所有 question_text / option_a~d / analysis 字段应用
text_cleaner.clean_question_text()，包括：
- C 代码块包裹为 markdown 代码围栏
- 子问题编号前加段落分隔
- 非代码区 \\n → 行尾双空格换行（markdown 原生）
- 清理 PDF 扫描多余字符
- 还原已有的 <br> 标签为 \\n 后重新处理（幂等）

用法:
    python scripts/clean_existing_questions.py [--dry-run] [--db PATH]

默认数据库路径: data/questions.db (相对于项目根目录)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# 确保能导入后端模块 — 直接导入 text_cleaner，避免触发完整 app 初始化链
_project_root = Path(__file__).resolve().parent.parent
_text_cleaner_path = _project_root / "backend" / "app" / "services" / "text_cleaner.py"
import importlib.util
_spec = importlib.util.spec_from_file_location("text_cleaner", str(_text_cleaner_path))
_text_cleaner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text_cleaner)
clean_question_text = _text_cleaner.clean_question_text

# 需要清洗的文本字段
TEXT_FIELDS = [
    "question_text",
    "option_a", "option_b", "option_c", "option_d",
    "analysis",
]


def clean_all(db_path: str, dry_run: bool = False) -> None:
    """遍历数据库所有题目，清洗文本字段。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 统计
    total = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    updated = 0
    skipped = 0

    print(f"数据库: {db_path}")
    print(f"题目总数: {total}")
    if dry_run:
        print("[DRY RUN] 不会写入数据库\n")
    else:
        print("开始清洗...\n")

    cur.execute("SELECT id, question_text, option_a, option_b, option_c, option_d, analysis FROM questions")

    batch = []
    for row in cur:
        qid = row["id"]
        changes = {}

        for field in TEXT_FIELDS:
            original = row[field]
            if original and isinstance(original, str):
                cleaned = clean_question_text(original)
                if cleaned != original:
                    changes[field] = cleaned

        if changes:
            if dry_run:
                print(f"  Q{qid}: 将更新 {len(changes)} 个字段 ({', '.join(changes.keys())})")
            else:
                set_clause = ", ".join(f"{k} = ?" for k in changes)
                values = list(changes.values()) + [qid]
                batch.append((set_clause, values))
            updated += 1
        else:
            skipped += 1

        # 每 200 条提交一次
        if not dry_run and len(batch) >= 200:
            for set_clause, values in batch:
                conn.execute(f"UPDATE questions SET {set_clause} WHERE id = ?", values)
            conn.commit()
            batch.clear()

    # 提交剩余
    if not dry_run and batch:
        for set_clause, values in batch:
            conn.execute(f"UPDATE questions SET {set_clause} WHERE id = ?", values)
        conn.commit()

    conn.close()

    print(f"\n完成！更新: {updated}, 跳过(无变化): {skipped}")


def main():
    parser = argparse.ArgumentParser(description="清洗数据库中所有题目的文本格式")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    parser.add_argument(
        "--db",
        default=str(_project_root / "data" / "questions.db"),
        help="数据库文件路径 (默认: data/questions.db)",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"错误: 数据库不存在 {args.db}", file=sys.stderr)
        sys.exit(1)

    clean_all(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
