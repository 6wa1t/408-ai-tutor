"""答题统计页面 — 正确率、薄弱知识点分析。"""

import streamlit as st
import requests

st.set_page_config(page_title="答题统计", page_icon="📊", layout="wide")

api_base = st.session_state.get("api_base", "http://localhost:8000")

st.title("📊 答题统计")

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
st.subheader("总体概览")

col1, col2, col3 = st.columns(3)
col1.metric("答题总数", stats.get("total_attempts", 0))
col2.metric("答对题数", stats.get("total_correct", 0))

accuracy = stats.get("accuracy", 0)
col3.metric("总正确率", f"{accuracy * 100:.1f}%")

# ─── Subject breakdown ───
st.divider()
st.subheader("各科统计")

subject_stats = stats.get("subject_stats", [])
if subject_stats:
    cols = st.columns(min(len(subject_stats), 4))
    for i, ss in enumerate(subject_stats):
        with cols[i % len(cols)]:
            st.markdown(f"**{ss.get('subject', '未知')}**")
            st.metric("正确率", f"{ss.get('accuracy', 0) * 100:.1f}%")
            st.caption(f"{ss.get('correct', 0)} / {ss.get('total', 0)} 题")
else:
    st.info("暂无答题记录，开始刷题后这里会显示各科统计。")

# ─── Weak knowledge points ───
st.divider()
st.subheader("薄弱知识点")

weak_knowledge = stats.get("weak_knowledge", [])
if weak_knowledge:
    st.markdown("以下是你掌握度最低的知识点，建议重点复习：")

    for i, wk in enumerate(weak_knowledge):
        mastery = wk.get("mastery_score", 0)
        tag = wk.get("tag", "未知")
        wrong = wk.get("wrong_count", 0)
        correct = wk.get("correct_count", 0)

        # Color coding based on mastery
        if mastery < 0.4:
            color = "🔴"
        elif mastery < 0.7:
            color = "🟡"
        else:
            color = "🟢"

        st.markdown(
            f"{color} **{tag}** — 掌握度 {mastery*100:.0f}% "
            f"(对{correct}题 / 错{wrong}题)"
        )
else:
    st.info("暂无薄弱知识点数据，多刷题后系统会自动分析。")

# ─── Recent quiz history ───
st.divider()
st.subheader("最近答题记录")

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
                icon = "✅" if record.get("is_correct") else "❌"
                st.markdown(
                    f"{icon} 题目 #{record.get('question_id', '')} — "
                    f"你的答案: **{record.get('user_answer', '')}** — "
                    f"{record.get('create_time', '')[:16]}"
                )
        else:
            st.info("暂无答题记录")
    else:
        st.info("获取历史记录失败")
except requests.ConnectionError:
    st.info("后端服务未连接")
