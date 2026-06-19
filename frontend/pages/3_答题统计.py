"""答题统计页面 — 正确率、薄弱知识点分析。"""

import sys
import os
import pathlib
import streamlit as st
import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.styles import apply_theme, gradient_header, glow_divider

st.set_page_config(page_title="答题统计", page_icon="📊", layout="wide")
apply_theme()

api_base = st.session_state.get("api_base", os.environ.get("API_BASE_URL", "http://localhost:8000"))

gradient_header("📊 答题统计", level=2)

# ─── Fetch stats from API ───
try:
    resp = requests.get(f"{api_base}/api/quiz/stats", timeout=10)
    if resp.status_code == 200:
        stats = resp.json()
    else:
        st.error("获取统计数据失败")
        st.stop()
except requests.ConnectionError:
    st.error("后端服务未连接，请先启动后端")
    st.stop()

# ─── Overall statistics ───
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">总体概览</h3>',
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)
col1.metric("答题总数", stats.get("total_attempts", 0))
col2.metric("答对题数", stats.get("total_correct", 0))

accuracy = stats.get("accuracy", 0)
col3.metric("总正确率", f"{accuracy * 100:.1f}%")

# ─── Subject breakdown ───
glow_divider()
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">各科统计</h3>',
    unsafe_allow_html=True,
)

subject_stats = stats.get("subject_stats", [])
if subject_stats:
    cols = st.columns(min(len(subject_stats), 4))
    for i, ss in enumerate(subject_stats):
        with cols[i % len(cols)]:
            subj_name = ss.get('subject', '未知')
            subj_acc = ss.get('accuracy', 0) * 100
            subj_correct = ss.get('correct', 0)
            subj_total = ss.get('total', 0)

            # Color code by accuracy
            if subj_acc >= 80:
                accent = "#22d3ee"  # cyan-green
            elif subj_acc >= 60:
                accent = "#f59e0b"  # amber
            else:
                accent = "#ef4444"  # red

            st.markdown(
                f'<div class="neon-card" style="border-left: 3px solid {accent}; padding: 16px; margin-bottom: 12px;">'
                f'<div style="font-weight:700; color:#e0e0f0; font-size:1rem; margin-bottom:8px;">'
                f'{subj_name}</div>'
                f'<div style="font-size:2rem; font-weight:800; color:{accent};">'
                f'{subj_acc:.1f}%</div>'
                f'<div style="color:#7878a0; font-size:0.85rem;">'
                f'{subj_correct} / {subj_total} 题</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
else:
    st.info("暂无答题记录，开始刷题后这里会显示各科统计。")

# ─── Weak knowledge points ───
glow_divider()
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">薄弱知识点</h3>',
    unsafe_allow_html=True,
)

weak_knowledge = stats.get("weak_knowledge", [])
if weak_knowledge:
    st.markdown(
        '<p style="color:#7878a0;margin-bottom:16px;">'
        '以下是你掌握度最低的知识点，建议重点复习：</p>',
        unsafe_allow_html=True,
    )

    for i, wk in enumerate(weak_knowledge):
        mastery = wk.get("mastery_score", 0)
        tag = wk.get("tag", "未知")
        wrong = wk.get("wrong_count", 0)
        correct = wk.get("correct_count", 0)

        # Color coding with severity class
        if mastery < 0.4:
            severity = "weak-red"
            bar_color = "#ef4444"
            mastery_text = "需重点复习"
        elif mastery < 0.7:
            severity = "weak-yellow"
            bar_color = "#f59e0b"
            mastery_text = "需加强练习"
        else:
            severity = "weak-green"
            bar_color = "#22d3ee"
            mastery_text = "掌握良好"

        bar_width = max(mastery * 100, 5)

        st.markdown(
            f'<div class="weak-item {severity}">'
            f'<div style="flex:1;">'
            f'<div style="font-weight:600;color:#e0e0f0;">{tag}</div>'
            f'<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">'
            f'<div style="flex:0 0 120px;height:6px;background:#1a1a3a;border-radius:3px;overflow:hidden;">'
            f'<div style="width:{bar_width}%;height:100%;background:{bar_color};border-radius:3px;"></div>'
            f'</div>'
            f'<span style="color:{bar_color};font-size:0.85rem;font-weight:600;">'
            f'{mastery*100:.0f}%</span>'
            f'<span style="color:#7878a0;font-size:0.8rem;">{mastery_text}</span>'
            f'</div>'
            f'</div>'
            f'<div style="text-align:right;color:#7878a0;font-size:0.85rem;white-space:nowrap;">'
            f'对{correct} / 错{wrong}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    st.info("暂无薄弱知识点数据，多刷题后系统会自动分析。")

# ─── Recent quiz history ───
glow_divider()
st.markdown(
    '<h3 class="gradient-text-sm" style="font-size:1.2rem;">最近答题记录</h3>',
    unsafe_allow_html=True,
)

try:
    resp = requests.get(
        f"{api_base}/api/quiz/history",
        params={"page": 1, "page_size": 20},
        timeout=10,
    )
    if resp.status_code == 200:
        history = resp.json()
        if history:
            for record in history:
                is_correct = record.get("is_correct")
                icon = "✅" if is_correct else "❌"
                accent = "#22d3ee" if is_correct else "#ef4444"
                qid = record.get('question_id', '')
                user_ans = record.get('user_answer', '')
                time_str = record.get('create_time', '')[:16]

                st.markdown(
                    f'<div class="history-row">'
                    f'<span style="font-size:1.1rem;">{icon}</span>'
                    f'<span style="color:#7878a0;">#{qid}</span>'
                    f'<span style="color:#e0e0f0;">你的答案: <strong style="color:{accent};">{user_ans}</strong></span>'
                    f'<span style="color:#7878a0;font-size:0.85rem;margin-left:auto;">{time_str}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("暂无答题记录")
    else:
        st.info("获取历史记录失败")
except requests.ConnectionError:
    st.info("后端服务未连接")
