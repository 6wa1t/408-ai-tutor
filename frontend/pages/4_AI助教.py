"""AI Tutor Chat Page — Streamlit frontend for DeepSeek-powered study assistant."""

import sys
import os
import pathlib
import streamlit as st
import requests
import json

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.styles import apply_theme, gradient_header, glow_divider, status_badge

st.set_page_config(page_title="AI助教", page_icon="🤖", layout="wide")
apply_theme()

api_base = st.session_state.get("api_base", os.environ.get("API_BASE_URL", "http://localhost:8000"))

# 保留最近20条对话（10轮），防止超出LLM上下文窗口
MAX_HISTORY = 20

gradient_header("🤖 408考研AI助教", level=2)
st.markdown(
    '<p class="tagline">基于DeepSeek大模型 · 专注408科目复习的智能助教</p>',
    unsafe_allow_html=True,
)


def check_status():
    """Check if LLM is configured."""
    try:
        resp = requests.get(f"{api_base}/api/tutor/status", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except requests.ConnectionError:
        return None
    return None


def send_chat(message: str, history: list, question_id: int | None = None):
    """Send chat message to API (non-streaming for simplicity)."""
    payload = {
        "message": message,
        "history": history,
        "temperature": st.session_state.get("temperature", 0.7),
    }
    if question_id:
        payload["question_id"] = question_id

    try:
        resp = requests.post(
            f"{api_base}/api/tutor/chat",
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["reply"]
        else:
            return f"❌ API错误 ({resp.status_code}): {resp.json().get('detail', '未知错误')}"
    except requests.ConnectionError:
        return "❌ 无法连接到后端服务，请确保 uvicorn 正在运行 (端口 8000)"
    except requests.Timeout:
        return "❌ 请求超时，AI助教响应时间较长，请稍后重试"


# ── Check LLM status ──
status = check_status()
if status is None:
    st.error("⚠️ 后端服务未启动。请先运行: `uvicorn app.main:app --reload`")
    st.stop()
elif not status.get("configured"):
    st.warning(
        "⚠️ DeepSeek API 未配置。请在项目根目录 `.env` 文件中设置你的 API Key:\n\n"
        "```\nLLM_API_KEY=sk-your-actual-key-here\n```"
    )
    st.stop()

# Custom status badge instead of st.success
model_name = status.get('model', 'unknown')
status_badge(f"AI助教已就绪 · {model_name}")

st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)


# ── Session state ──
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "temperature" not in st.session_state:
    st.session_state.temperature = 0.7


# ── Sidebar settings ──
with st.sidebar:
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1.1rem;">⚙️ 设置</h3>',
        unsafe_allow_html=True,
    )
    st.session_state.temperature = st.slider(
        "Temperature", 0.0, 1.5, 0.7, 0.1,
        help="越高越有创意，越低越严谨"
    )

    glow_divider()
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1rem;">🎯 快捷提问</h3>',
        unsafe_allow_html=True,
    )
    quick_prompts = [
        "请帮我梳理数据结构的知识点框架",
        "解释一下进程和线程的区别",
        "Cache映射方式有哪些？各自优缺点？",
        "TCP三次握手的过程和原因",
        "帮我分析这道题的解题思路",
        "408考研各科的分值占比是多少？",
        "请给我制定一个30天的408复习计划",
    ]
    for prompt in quick_prompts:
        if st.button(prompt, use_container_width=True):
            st.session_state.pending_message = prompt
            st.rerun()

    glow_divider()
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()


# ── Display chat history ──
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])


# ── Handle pending message from sidebar ──
if "pending_message" in st.session_state:
    user_msg = st.session_state.pop("pending_message")
    st.session_state.chat_history.append({"role": "user", "content": user_msg})

    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_msg)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("AI助教正在思考..."):
            reply = send_chat(user_msg, st.session_state.chat_history[-(MAX_HISTORY+1):-1])
        st.markdown(reply)

    st.session_state.chat_history.append({"role": "assistant", "content": reply})
    st.rerun()


# ── User input ──
user_input = st.chat_input("向AI助教提问... (例如: 解释一下B+树和B树的区别)")

if user_input:
    # Add user message
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    # Get AI reply
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("AI助教正在思考..."):
            reply = send_chat(user_input, st.session_state.chat_history[-(MAX_HISTORY+1):-1])
        st.markdown(reply)

    st.session_state.chat_history.append({"role": "assistant", "content": reply})
