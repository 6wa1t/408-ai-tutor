"""迁移脚本 — 已废弃，保留仅作历史记录。

⚠️ 警告：flowus_synced 列是 cron 定时任务增量同步的关键字段，
   禁止从 misconceptions 表中删除。此脚本已改为空操作。

如需查看 misconceptions 表结构，请使用：
    python -c "import sqlite3; conn=sqlite3.connect('data/questions.db'); \
               print([r[1] for r in conn.execute('PRAGMA table_info(misconceptions)')])"
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data" / "questions.db"


def check_schema() -> None:
    """仅检查表结构，不做任何修改。"""
    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(misconceptions)")]
        print(f"misconceptions 表当前列: {cols}")

        if "flowus_synced" in cols:
            print("✅ flowus_synced 列存在（正常，cron 增量同步依赖此列）")
        else:
            print("⚠️ flowus_synced 列缺失！请立即恢复：")
            print("   ALTER TABLE misconceptions ADD COLUMN flowus_synced INTEGER DEFAULT 0")

        count = conn.execute("SELECT COUNT(*) FROM misconceptions").fetchone()[0]
        synced = conn.execute(
            "SELECT COUNT(*) FROM misconceptions WHERE flowus_synced=1"
        ).fetchone()[0] if "flowus_synced" in cols else "?"
        print(f"记录总数: {count}，已同步: {synced}")
    finally:
        conn.close()


if __name__ == "__main__":
    check_schema()
