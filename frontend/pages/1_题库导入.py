"""题库导入页面 — 上传PDF或指定目录导入题目。"""

import sys
import pathlib
import streamlit as st
import requests

# Streamlit pages need explicit path setup to find shared/ module
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.styles import apply_theme, gradient_header, glow_divider
from shared.api import get_api_base

st.set_page_config(page_title="题库导入", page_icon="📥", layout="wide")
apply_theme()

# Get API base from session state or default
api_base = get_api_base()

gradient_header("📥 题库导入", level=2)


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


tab1, tab2 = st.tabs(["📄 上传PDF文件", "📂 指定目录导入"])

# ─── Tab 1: Upload single PDF ───
with tab1:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '上传一个408题库PDF文件，系统将自动解析题目并入库。</p>',
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "选择PDF文件",
        type=["pdf"],
        help="支持408统考真题、模拟题等题库PDF",
    )

    if st.button("📤 上传并导入", type="primary"):
        if uploaded_file is None:
            st.warning("请先选择一个PDF文件")
        else:
            with st.spinner("正在解析PDF并导入题目..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                    response = requests.post(
                        f"{api_base}/api/import/upload",
                        files=files,
                        timeout=120,
                    )

                    if response.status_code == 200:
                        report = response.json()
                        st.success("✨ 导入完成！")
                        _show_report(report)
                    else:
                        st.error(f"导入失败: {response.json().get('detail', response.text)}")
                except requests.ConnectionError:
                    st.error(f"无法连接到后端服务 ({api_base})，请确认后端已启动。")
                except Exception as e:
                    st.error(f"导入出错: {e}")

# ─── Tab 2: Directory import ───
with tab2:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '指定一个包含多个PDF文件的目录路径，系统将批量导入所有题库。</p>',
        unsafe_allow_html=True,
    )

    directory = st.text_input(
        "PDF目录路径",
        placeholder="例如: D:/题库/408真题",
        help="输入包含PDF题库文件的目录绝对路径",
    )

    if st.button("📂 批量导入", type="primary"):
        if not directory:
            st.warning("请输入目录路径")
        else:
            with st.spinner("正在批量导入所有PDF..."):
                try:
                    response = requests.post(
                        f"{api_base}/api/import/directory",
                        data={"directory": directory},
                        timeout=300,
                    )

                    if response.status_code == 200:
                        report = response.json()
                        st.success("✨ 批量导入完成！")
                        _show_report(report)
                    else:
                        st.error(f"导入失败: {response.json().get('detail', response.text)}")
                except requests.ConnectionError:
                    st.error(f"无法连接到后端服务 ({api_base})，请确认后端已启动。")
                except Exception as e:
                    st.error(f"导入出错: {e}")

# ─── Show current database stats ───
glow_divider()
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">📊 当前题库概况</h3>',
    unsafe_allow_html=True,
)

try:
    resp = requests.get(f"{api_base}/api/questions/stats", timeout=5)
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
                st.info("题库为空，请先导入PDF")
    else:
        st.info("请先启动后端服务")
except requests.ConnectionError:
    st.info("后端服务未连接，启动后可查看题库统计")
