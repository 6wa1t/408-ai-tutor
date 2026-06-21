"""
Post-Import Processing Script — 导入后一键处理
=================================================

Usage:
    python scripts/post_import_process.py                    # 完整处理所有科目
    python scripts/post_import_process.py --subject 数据结构  # 只处理指定科目
    python scripts/post_import_process.py --dry-run          # 预览模式，不修改

处理内容：
    1. 从源PDF提取题目配图 → 保存到 images/questions/ 并写入DB
    2. 修复PUA私有字符乱码 → 将 U+F0xx 映射为标准 Unicode 符号

依赖：
    - 后端依赖已安装 (pip install -r backend/requirements.txt)
    - PDF文件位于配置的 data/ 目录（或通过 --pdf-dir 指定）
    - 数据库位于 data/questions.db
"""

import argparse
import os
import re
import sys
import sqlite3
from pathlib import Path

# ── 路径配置 ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "questions.db"
DEFAULT_PDF_DIR = PROJECT_ROOT / "data"

sys.stdout.reconfigure(encoding="utf-8")


# ═══════════════════════════════════════════════
# 模块一：图片提取（直接使用SQLite+PyMuPDF）
# ═══════════════════════════════════════════════

def extract_images(pdf_dir: str, subject_filter: str | None = None,
                   dry_run: bool = False) -> dict:
    """从源PDF提取配图并关联到数据库题目。

    策略：
    1. 扫描 data/ 目录所有 PDF 文件
    2. 对每个 PDF，逐页提取图片（≥200x150）
    3. 通过文本指纹匹配题目页码
    4. 将图片路径写入 question.image_path 字段
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {"error": "缺少 PyMuPDF，请执行: pip install PyMuPDF"}

    image_dir = PROJECT_ROOT / "images"
    MIN_W, MIN_H = 200, 150
    FINGERPRINT_LEN = 40
    PUA_RE = re.compile(r'[\ue000-\uf8ff]')

    def normalize(text: str) -> str:
        return re.sub(r'\s+', '', PUA_RE.sub('', text or ''))

    def fingerprint(text: str) -> str:
        return normalize(text)[:FINGERPRINT_LEN]

    def infer_subject(path: str) -> str:
        name = Path(path).name.lower()
        if "数据结构" in name: return "数据结构"
        if "操作系统" in name: return "操作系统"
        if "组成原理" in name or "计算机组成" in name: return "计算机组成原理"
        if "计算机网络" in name or "计网" in name: return "计算机网络"
        return "未知"

    # ── 连接DB ──
    if not DB_PATH.exists():
        return {"error": f"数据库不存在: {DB_PATH}"}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ── 收集所有 source_pdf ──
    query = "SELECT DISTINCT source_pdf FROM questions WHERE source_pdf IS NOT NULL"
    params = []
    if subject_filter:
        query += " AND subject = ?"
        params.append(subject_filter)
    source_pdfs = [r["source_pdf"] for r in cursor.execute(query, params).fetchall()]

    if not source_pdfs:
        conn.close()
        return {"error": "数据库中无题目记录，请先导入PDF"}

    # ── 扫描PDF目录 ──
    pdf_dir_path = Path(pdf_dir)
    all_pdfs = {}
    for f in pdf_dir_path.rglob("*.pdf"):
        all_pdfs[f.name.lower()] = str(f)

    # ── 逐PDF处理 ──
    total_images = 0
    total_updated = 0
    processed_pdfs = 0
    skipped_pdfs = []

    for source_name in source_pdfs:
        # 查找源PDF文件
        pdf_path = all_pdfs.get(source_name.lower())
        if not pdf_path:
            # fallback: 匹配 stem
            target_stem = Path(source_name).stem.lower()
            for fname, fpath in all_pdfs.items():
                if Path(fname).stem.lower() == target_stem:
                    pdf_path = fpath
                    break
        if not pdf_path:
            skipped_pdfs.append(source_name)
            continue

        subject = infer_subject(pdf_path)
        source_stem = Path(pdf_path).stem

        # 获取该PDF对应的所有DB题目
        rows = cursor.execute(
            "SELECT id, question_text FROM questions WHERE source_pdf = ? ORDER BY id",
            (source_name,)
        ).fetchall()

        if not rows:
            continue

        print(f"  [{source_name}] {len(rows)} 道题")

        # 构建题目的文本指纹
        q_fingerprints = {}
        for r in rows:
            fp = fingerprint(r["question_text"])
            if len(fp) >= 5:
                q_fingerprints[r["id"]] = fp

        # 打开PDF，逐页匹配
        doc = fitz.open(pdf_path)
        processed_pdfs += 1

        for page_idx in range(len(doc)):
            page = doc[page_idx]

            # 提取该页文本指纹
            page_text = normalize(page.get_text("text"))

            # 找出匹配到该页的题目
            matched_qids = []
            for qid, fp in q_fingerprints.items():
                if fp in page_text:
                    matched_qids.append(qid)

            if not matched_qids:
                continue

            # 提取该页图片
            q_positions = []
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(s.get("text", "") for s in line.get("spans", []))
                    m = re.match(r"^\s*(\d{1,4})\s*[.、．]\s*\S", line_text)
                    if m:
                        q_positions.append((int(m.group(1)), line["bbox"][1]))
            q_positions.sort(key=lambda t: t[1])

            for img_idx, info in enumerate(page.get_image_info()):
                xref = info.get("xref", 0)
                w, h = info.get("width", 0), info.get("height", 0)
                if w < MIN_W or h < MIN_H:
                    continue
                if not xref:
                    continue

                try:
                    img_dict = doc.extract_image(xref)
                except Exception:
                    continue
                if not img_dict or not img_dict.get("image"):
                    continue

                ext = img_dict.get("ext", "jpeg")
                img_filename = f"{source_stem}_p{page_idx:03d}_img{img_idx:03d}.{ext}"
                rel_path = f"questions/{subject}/{img_filename}"

                # 匹配到最近的题目号
                img_y = info.get("bbox", (0, 0, 0, 0))[1]
                matched_qnum = None
                best_dist = float("inf")
                for qnum, qy in q_positions:
                    if qy <= img_y and (img_y - qy) < best_dist:
                        best_dist = img_y - qy
                        matched_qnum = qnum

                # 更新该页所有匹配题目的 image_path
                for qid in matched_qids:
                    if dry_run:
                        print(f"    [DRY-RUN] Q#{qid} -> {rel_path}")
                    else:
                        # 保存图片文件
                        abs_path = image_dir / rel_path
                        abs_path.parent.mkdir(parents=True, exist_ok=True)
                        abs_path.write_bytes(img_dict["image"])

                        # 更新DB
                        existing = cursor.execute(
                            "SELECT image_path FROM questions WHERE id = ?", (qid,)
                        ).fetchone()
                        cur_paths = [p.strip() for p in (existing["image_path"] or "").split(",") if p.strip()]
                        if rel_path not in cur_paths:
                            cur_paths.append(rel_path)
                            cursor.execute(
                                "UPDATE questions SET image_path = ? WHERE id = ?",
                                (",".join(cur_paths), qid)
                            )

                    total_images += 1
                    total_updated += 1

        doc.close()

    if not dry_run:
        conn.commit()

    conn.close()

    return {
        "processed_pdfs": processed_pdfs,
        "images_extracted": total_images,
        "questions_updated": total_updated,
        "skipped_pdfs": skipped_pdfs,
    }


# ═══════════════════════════════════════════════
# 模块二：PUA字符修复
# ═══════════════════════════════════════════════

PUA_RE = re.compile(r'[\ue000-\uf8ff]')

PAIRED_REPLACEMENTS = [
    ('\uf0ee', '(', ')'),       # 括号 O(n²)
    ('\uf0f6', '[', ']'),       # 方括号 A[0..n]
    ('\uf0f4', '|', '|'),       # 绝对值 |V|
    ('\uf0f7', '\u230a', '\u230b'),  # 下取整 ⌊x⌋
    ('\uf0f8', '\u2308', '\u2309'),  # 上取整 ⌈x⌉
]

SINGLE_REPLACEMENTS = {
    '\uf0e0': '',               # ⟨ 冗余左尖括号
    '\uf0e1': '',               # 分隔符
    '\uf0e2': '',               # ⟩ 冗余右尖括号
    '\uf00a': "'",              # ′ 上标
    '\uf0e8': '\u23a7',         # ⎧ 左花括号上段
    '\uf0e9': '\u23ab',         # ⎫ 右花括号上段
    '\uf0ea': '\u23aa',         # ⎪ 花括号延伸
    '\uf0e3': '\u23a7',         # ⎧ 分段函数左括号
    '\uf0e4': '\u222a',         # ∪ 并集
    '\uf0b1': '\u2211',         # ∑ 求和
    '\uf0dc': '\u0305',         # ̅ 组合上划线
    '\uf0fb': '\u23df',         # ⏟ 下花括号
    '\uf0fc': '\u23df',
    '\uf0fd': '\u23df',
}

FIELDS = ["question_text", "option_a", "option_b", "option_c", "option_d", "analysis"]


def has_pua(text: str) -> bool:
    return bool(text and PUA_RE.search(text))


def repair_text(text: str) -> str:
    if not text:
        return text
    # 配对括号修复
    for pua_ch, open_ch, close_ch in PAIRED_REPLACEMENTS:
        pattern = re.escape(pua_ch) + r'\s+' + re.escape(pua_ch)
        text = re.sub(pattern, open_ch + close_ch, text)
        text = text.replace(pua_ch, open_ch)
    # 单字符替换
    for pua_ch, replacement in SINGLE_REPLACEMENTS.items():
        text = text.replace(pua_ch, replacement)
    return text


def fix_pua(subject_filter: str | None = None, dry_run: bool = False) -> dict:
    """扫描数据库题目，修复PUA乱码字符。"""
    if not DB_PATH.exists():
        return {"error": f"数据库不存在: {DB_PATH}"}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 找出含PUA的题目
    query = "SELECT id, subject, " + ", ".join(FIELDS) + " FROM questions"
    params = []
    if subject_filter:
        query += " WHERE subject = ?"
        params.append(subject_filter)
    rows = cursor.execute(query, params).fetchall()

    affected = []
    for r in rows:
        for f in FIELDS:
            if has_pua(r[f]):
                affected.append(r["id"])
                break

    print(f"\n  PUA乱码检测: {len(affected)} 道题含PUA字符 (共 {len(rows)} 道)")

    if not affected:
        conn.close()
        return {"fixed": 0, "total_affected": 0}

    # 执行修复
    fixed = 0
    for qid in affected:
        row = cursor.execute(
            "SELECT " + ", ".join(FIELDS) + " FROM questions WHERE id = ?",
            (qid,)
        ).fetchone()

        updates = {}
        for f in FIELDS:
            text = row[f]
            if text and has_pua(text):
                if dry_run:
                    before = text[:60].replace("\n", " ")
                    after = repair_text(text)[:60].replace("\n", " ")
                    if before != after:
                        print(f"    [DRY-RUN] Q#{qid} ({row['subject']}) {f}:")
                        print(f"      前: {before}")
                        print(f"      后: {after}")
                else:
                    updates[f] = repair_text(text)

        if updates:
            set_clause = ", ".join(f"{f} = ?" for f in updates)
            values = list(updates.values()) + [qid]
            cursor.execute(
                f"UPDATE questions SET {set_clause} WHERE id = ?",
                values
            )
            fixed += 1

    if not dry_run:
        conn.commit()

    # 验证
    remaining = cursor.execute(
        "SELECT COUNT(*) FROM questions WHERE "
        + " OR ".join(f"{f} LIKE '%\ue000%' OR {f} LIKE '%\uf0ee%' OR {f} LIKE '%\uf0f6%' OR {f} LIKE '%\uf0f4%' OR {f} LIKE '%\uf0f7%' OR {f} LIKE '%\uf0f8%' OR {f} LIKE '%\uf0e0%' OR {f} LIKE '%\uf0e1%'" for f in FIELDS)
    ).fetchone()[0]

    conn.close()

    return {
        "total_affected": len(affected),
        "fixed": fixed,
        "remaining": remaining,
    }


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="导入后处理：提取题目配图 + 修复PUA乱码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/post_import_process.py                    # 完整处理
  python scripts/post_import_process.py --subject 数据结构  # 只处理数据结构
  python scripts/post_import_process.py --pdf-dir D:/408题库 # 指定PDF目录
  python scripts/post_import_process.py --dry-run          # 预览模式
  python scripts/post_import_process.py --skip-images      # 只修复PUA
  python scripts/post_import_process.py --skip-pua         # 只提取图片
        """
    )
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR),
                        help="源PDF目录 (默认: data/)")
    parser.add_argument("--subject", default=None,
                        help="只处理指定科目 (如: 数据结构)")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式，不修改数据库和文件")
    parser.add_argument("--skip-images", action="store_true",
                        help="跳过图片提取，只修复PUA")
    parser.add_argument("--skip-pua", action="store_true",
                        help="跳过PUA修复，只提取图片")
    args = parser.parse_args()

    print("=" * 60)
    print("  408-AI-Tutor 导入后处理")
    print("=" * 60)
    if args.dry_run:
        print("  [预览模式] 不会修改任何数据\n")

    if args.subject:
        print(f"  限定科目: {args.subject}\n")

    # ── 模块一：图片提取 ──
    if not args.skip_images:
        print("📷 [1/2] 提取题目配图...")
        img_result = extract_images(
            pdf_dir=args.pdf_dir,
            subject_filter=args.subject,
            dry_run=args.dry_run,
        )
        if "error" in img_result:
            print(f"  ⚠️ {img_result['error']}")
        else:
            print(f"  ✅ 处理 {img_result['processed_pdfs']} 个PDF")
            print(f"  ✅ 提取 {img_result['images_extracted']} 张图片")
            print(f"  ✅ 更新 {img_result['questions_updated']} 道题")
            if img_result["skipped_pdfs"]:
                print(f"  ⚠️ {len(img_result['skipped_pdfs'])} 个PDF未找到:")
                for s in img_result["skipped_pdfs"][:5]:
                    print(f"      - {s}")
        print()

    # ── 模块二：PUA修复 ──
    if not args.skip_pua:
        print("🔤 [2/2] 修复PUA乱码...")
        pua_result = fix_pua(
            subject_filter=args.subject,
            dry_run=args.dry_run,
        )
        if "error" in pua_result:
            print(f"  ⚠️ {pua_result['error']}")
        else:
            print(f"  ✅ 检测到 {pua_result['total_affected']} 道含PUA的题")
            print(f"  ✅ 修复 {pua_result['fixed']} 道题")
            if pua_result["remaining"] > 0:
                print(f"  ⚠️ 仍有 {pua_result['remaining']} 道题残留PUA (需运行 repair_garbled_text.py)")
            else:
                print(f"  ✅ 全部修复完成！")
        print()

    # ── 总结 ──
    print("=" * 60)
    if args.dry_run:
        print("  [预览模式] 未修改任何数据")
        print("  移除 --dry-run 执行实际修改")
    else:
        print("  ✅ 后处理完成！")
        print("  请重启前端以刷新数据")
    print("=" * 60)


if __name__ == "__main__":
    main()
