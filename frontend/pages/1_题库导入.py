"""题库导入页面 — 支持 Markdown / 文字型PDF / 扫描型PDF / 预置题库 四种导入方式。"""

import sys
import pathlib
import streamlit as st
import requests

# Streamlit pages need explicit path setup to find shared/ module
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.styles import apply_theme, gradient_header, glow_divider
from shared.api import get_api_base
from shared.bank_labels import format_bank_option_label

st.set_page_config(page_title="题库导入", page_icon="📥", layout="wide")
apply_theme()

# Get API base from session state or default
api_base = get_api_base()

gradient_header("📥 题库导入", level=2)

st.info(
    "推荐使用 **Markdown 导入**（先用 [MinerU](https://github.com/opendatalab/MinerU) 转换 PDF 为 Markdown），"
    "效果最佳、速度最快。",
    icon="💡",
)


def _show_report(report: dict):
    """Display import report in a nice format."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("检测到", report.get("total_questions", 0), "题")
    col2.metric("成功导入", report.get("total_success", 0), "题")
    col3.metric("跳过(重复)", report.get("total_skipped", 0), "题")
    col4.metric("失败", report.get("total_errors", 0), "题")

    # File-level details
    file_results = report.get("file_results", [])
    if file_results:
        with st.expander("📋 查看各文件详情"):
            for fr in file_results:
                status_icon = "✅" if fr.get("error_count", 0) == 0 else "⚠️"
                st.markdown(
                    f"{status_icon} **{fr['filename']}**: "
                    f"检测 {fr.get('total_found', 0)} 题, "
                    f"导入 {fr.get('success_count', 0)}, "
                    f"跳过 {fr.get('skipped_count', 0)}, "
                    f"失败 {fr.get('error_count', 0)}"
                )
                errors = fr.get("errors", [])
                if errors:
                    for err in errors[:5]:
                        st.caption(f"  ⚠️ {err}")
                    if len(errors) > 5:
                        st.caption(f"  ... 及其他 {len(errors) - 5} 个错误")


def _do_upload_import(file_obj, import_mode: str, file_name: str, mime_type: str):
    """Upload a file and show results."""
    timeout_map = {"text_pdf": 120, "scanned_pdf": 1200, "markdown": 120}
    timeout = timeout_map.get(import_mode, 120)

    spinner_msg = {
        "text_pdf": "正在解析文字型PDF...",
        "scanned_pdf": "正在使用千问VL-Max识别扫描型PDF（请耐心等待）...",
        "markdown": "正在解析Markdown文件...",
    }.get(import_mode, "正在导入...")

    with st.spinner(spinner_msg):
        try:
            files = {"file": (file_name, file_obj, mime_type)}
            data = {"import_mode": import_mode, "auto_process": "true"}
            response = requests.post(
                f"{api_base}/api/import/upload",
                files=files,
                data=data,
                timeout=timeout,
            )

            if response.status_code == 200:
                report = response.json()
                st.success("✨ 导入完成！")
                _show_report(report)
            else:
                st.error(f"导入失败: {response.json().get('detail', response.text)}")
        except requests.ConnectionError:
            st.error(f"无法连接到后端服务 ({api_base})，请确认后端已启动。")
        except requests.Timeout:
            st.error("导入超时，扫描型PDF可能需要更长时间，请重试。")
        except Exception as e:
            st.error(f"导入出错: {e}")


def _do_directory_import(directory: str, import_mode: str):
    """Import from a directory and show results."""
    timeout_map = {"text_pdf": 300, "scanned_pdf": 1800, "markdown": 300}
    timeout = timeout_map.get(import_mode, 300)

    spinner_msg = {
        "text_pdf": "正在批量导入文字型PDF...",
        "scanned_pdf": "正在批量识别扫描型PDF（请耐心等待）...",
        "markdown": "正在批量导入Markdown文件...",
    }.get(import_mode, "正在导入...")

    with st.spinner(spinner_msg):
        try:
            response = requests.post(
                f"{api_base}/api/import/directory",
                data={
                    "directory": directory,
                    "import_mode": import_mode,
                    "auto_process": "true",
                },
                timeout=timeout,
            )

            if response.status_code == 200:
                report = response.json()
                st.success("✨ 批量导入完成！")
                _show_report(report)
            else:
                st.error(f"导入失败: {response.json().get('detail', response.text)}")
        except requests.ConnectionError:
            st.error(f"无法连接到后端服务 ({api_base})，请确认后端已启动。")
        except requests.Timeout:
            st.error("导入超时，请重试或减少文件数量。")
        except Exception as e:
            st.error(f"导入出错: {e}")


# ─── Four tabs ───
tab_md, tab_text, tab_scan, tab_bank = st.tabs([
    "📝 Markdown导入",
    "📄 文字型PDF导入",
    "🔍 扫描型PDF导入",
    "📦 自选题库",
])

# ─── Tab 1: Markdown Import (Recommended) ───
with tab_md:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '导入 MinerU 转换的 Markdown 文件，效果最佳。支持完整的题目文本、数学公式和配图。</p>',
        unsafe_allow_html=True,
    )

    md_sub = st.tabs(["上传 .md 文件", "指定目录导入"])

    with md_sub[0]:
        md_file = st.file_uploader(
            "选择 Markdown 文件",
            type=["md"],
            help="上传 MinerU 转换输出的 .md 文件（同目录需有 images/ 文件夹）",
            key="md_upload",
        )

        if st.button("📤 导入 Markdown", type="primary", key="btn_md_upload"):
            if md_file is None:
                st.warning("请先选择一个 .md 文件")
            else:
                _do_upload_import(
                    md_file.getvalue(), "markdown",
                    md_file.name, "text/markdown",
                )

    with md_sub[1]:
        md_dir = st.text_input(
            "Markdown 目录路径",
            placeholder="例如: D:/mineru_output/【A4留白】计算机组成原理综合题做题本/txt",
            help="包含 .md 文件的目录（会递归搜索所有 .md 文件）",
            key="md_dir",
        )

        if st.button("📂 批量导入 Markdown", type="primary", key="btn_md_dir"):
            if not md_dir:
                st.warning("请输入目录路径")
            else:
                _do_directory_import(md_dir, "markdown")

# ─── Tab 2: Text PDF Import ───
with tab_text:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '适用于文字型PDF（可直接选中复制文字的PDF）。使用 PyMuPDF 快速提取，免费无API消耗。</p>',
        unsafe_allow_html=True,
    )

    text_sub = st.tabs(["上传 PDF 文件", "指定目录导入"])

    with text_sub[0]:
        pdf_file_text = st.file_uploader(
            "选择 PDF 文件",
            type=["pdf"],
            help="支持408统考真题、模拟题等文字型题库PDF",
            key="pdf_upload_text",
        )

        if st.button("📤 上传并导入", type="primary", key="btn_pdf_text_upload"):
            if pdf_file_text is None:
                st.warning("请先选择一个 PDF 文件")
            else:
                _do_upload_import(
                    pdf_file_text.getvalue(), "text_pdf",
                    pdf_file_text.name, "application/pdf",
                )

    with text_sub[1]:
        pdf_dir_text = st.text_input(
            "PDF 目录路径",
            placeholder="例如: D:/题库/408真题",
            help="输入包含PDF题库文件的目录绝对路径",
            key="pdf_dir_text",
        )

        if st.button("📂 批量导入", type="primary", key="btn_pdf_text_dir"):
            if not pdf_dir_text:
                st.warning("请输入目录路径")
            else:
                _do_directory_import(pdf_dir_text, "text_pdf")

# ─── Tab 3: Scanned PDF Import ───
with tab_scan:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '适用于扫描型PDF（页面为图片、无法选中文字）。使用千问 VL-Max 视觉模型逐页识别。</p>',
        unsafe_allow_html=True,
    )
    st.warning(
        "扫描型PDF导入使用千问 VL-Max 视觉模型，耗时较长（约2-5分钟/页）且产生 API 费用。"
        "建议优先使用 Markdown 导入。",
        icon="💰",
    )

    scan_sub = st.tabs(["上传 PDF 文件", "指定目录导入"])

    with scan_sub[0]:
        pdf_file_scan = st.file_uploader(
            "选择扫描型 PDF 文件",
            type=["pdf"],
            help="上传扫描版（图片型）PDF题库",
            key="pdf_upload_scan",
        )

        if st.button("📤 上传并导入", type="primary", key="btn_pdf_scan_upload"):
            if pdf_file_scan is None:
                st.warning("请先选择一个 PDF 文件")
            else:
                _do_upload_import(
                    pdf_file_scan.getvalue(), "scanned_pdf",
                    pdf_file_scan.name, "application/pdf",
                )

    with scan_sub[1]:
        pdf_dir_scan = st.text_input(
            "PDF 目录路径",
            placeholder="例如: D:/题库/扫描件",
            help="输入包含扫描型PDF文件的目录绝对路径",
            key="pdf_dir_scan",
        )

        if st.button("📂 批量导入", type="primary", key="btn_pdf_scan_dir"):
            if not pdf_dir_scan:
                st.warning("请输入目录路径")
            else:
                _do_directory_import(pdf_dir_scan, "scanned_pdf")

# ─── Tab 4: Pre-built Question Bank ───
with tab_bank:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '从预置题库中选择题集，一键导入到当前数据库。题库经过验证，格式完整。</p>',
        unsafe_allow_html=True,
    )

    # Fetch available banks
    try:
        resp = requests.get(f"{api_base}/api/import/banks", timeout=10)
        if resp.status_code == 200:
            banks_data = resp.json()
            banks = banks_data.get("banks", [])
        else:
            banks = []
    except requests.ConnectionError:
        banks = []

    if not banks:
        st.info(
            "暂无可用的预置题库。你可以通过以下方式添加：\n\n"
            "1. 先用上面的导入方式导入题目\n"
            "2. 验证无误后，在终端运行 `python scripts/export_bank.py --all` 导出题库包\n"
            "3. 将 `question_banks/` 目录上传到 GitHub，其他用户即可直接使用"
        )
    else:
        # Show available banks as selectable list
        bank_options = {}
        for b in banks:
            label = format_bank_option_label(b)
            bank_options[label] = b["id"]

        selected = st.multiselect(
            "选择要导入的题库",
            options=list(bank_options.keys()),
            help="可多选，系统将自动去重（已存在的题目不会重复导入）",
        )

        if st.button("📦 导入选中题库", type="primary", key="btn_bank_import"):
            if not selected:
                st.warning("请至少选择一个题库")
            else:
                for label in selected:
                    bank_id = bank_options[label]
                    with st.spinner(f"正在导入 {label}..."):
                        try:
                            resp = requests.post(
                                f"{api_base}/api/import/banks/{bank_id}",
                                timeout=60,
                            )
                            if resp.status_code == 200:
                                result = resp.json()
                                st.success(
                                    f"✅ {result.get('bank_name', bank_id)}: "
                                    f"导入 {result.get('imported', 0)} 题, "
                                    f"跳过 {result.get('skipped', 0)} 题（已存在）"
                                )
                            else:
                                st.error(
                                    f"❌ {bank_id}: "
                                    f"{resp.json().get('detail', resp.text)}"
                                )
                        except Exception as e:
                            st.error(f"❌ {bank_id}: {e}")

# ─── Show current database stats ───
glow_divider()
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">📊 当前题库概况</h3>',
    unsafe_allow_html=True,
)

try:
    resp = requests.get(f"{api_base}/api/questions/stats", timeout=15)
    if resp.status_code == 200:
        stats = resp.json()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("题目总数", stats.get("total", 0))

        by_subject = stats.get("by_subject", {})
        with col2:
            if by_subject:
                st.markdown("**各科题目数:**")
                for subj, cnt in by_subject.items():
                    st.markdown(
                        f'<div class="history-row" style="padding:4px 12px;">'
                        f'<span style="color:#00f0ff;">●</span> {subj}: <strong>{cnt}</strong> 题'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("题库为空，请先导入题库")
    else:
        st.info("请先启动后端服务")
except requests.ConnectionError:
    st.info("后端服务未连接，启动后可查看题库统计")
