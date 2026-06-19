"""408考研AI专属助教 — Streamlit Frontend Entry Point.

Run with:
    streamlit run frontend/app.py
"""

import sys
import os
import pathlib
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from shared.styles import apply_theme, gradient_header, neon_card, glow_divider

# Default API URL: support Docker env var, fall back to localhost
_DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="408考研AI助教",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# ── Hero Section ──
gradient_header("📚 408考研AI专属助教")
st.markdown(
    '<p class="tagline">你的专属AI考研助教 · 智能刷题 · 精准分析</p>',
    unsafe_allow_html=True,
)

# ── Feature Cards ──
col1, col2, col3 = st.columns(3)

with col1:
    neon_card(
        "📥 题库导入",
        "上传408题库PDF，自动解析题目并入库。<br>"
        "支持单文件上传和批量目录导入。",
        "cyan",
    )

with col2:
    neon_card(
        "✏️ 刷题练习",
        "随机抽题或按章节顺序刷题，<br>"
        "即时批改、查看详细解析。",
        "purple",
    )

with col3:
    neon_card(
        "📊 答题统计",
        "追踪正确率变化趋势，<br>"
        "智能分析薄弱知识点。",
        "magenta",
    )

glow_divider()

# ── Quick Start Guide ──
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.3rem;margin-bottom:16px;">'
    '🚀 快速开始</h3>',
    unsafe_allow_html=True,
)

guide_col1, guide_col2, guide_col3 = st.columns(3)

with guide_col1:
    st.markdown(
        '<div class="neon-card" style="text-align:center;padding:20px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">①</div>'
        '<p style="color:#e0e0f0;margin:0;">在「题库导入」页面<br>上传PDF题库文件</p>'
        '</div>',
        unsafe_allow_html=True,
    )

with guide_col2:
    st.markdown(
        '<div class="neon-card" style="text-align:center;padding:20px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">②</div>'
        '<p style="color:#e0e0f0;margin:0;">到「刷题练习」<br>开始做题</p>'
        '</div>',
        unsafe_allow_html=True,
    )

with guide_col3:
    st.markdown(
        '<div class="neon-card" style="text-align:center;padding:20px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">③</div>'
        '<p style="color:#e0e0f0;margin:0;">在「答题统计」<br>查看学习分析</p>'
        '</div>',
        unsafe_allow_html=True,
    )

glow_divider()

# ── API Status ──
st.markdown(
    '<div style="color:#7878a0;font-size:0.85rem;text-align:center;margin-top:16px;">'
    '后端API默认运行在 <code style="color:#00f0ff;">http://localhost:8000</code>'
    ' · API文档: <code style="color:#00f0ff;">http://localhost:8000/docs</code>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Sidebar Settings ──
with st.sidebar:
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1.1rem;">⚙️ 设置</h3>',
        unsafe_allow_html=True,
    )
    api_base = st.text_input(
        "后端API地址",
        value=_DEFAULT_API_BASE,
        key="api_base",
    )
