"""AI Tutor Chat Page — Streamlit frontend for DeepSeek-powered study assistant.

Features conversation history persistence via backend API.
"""

import sys
import os
import pathlib
import streamlit as st
import requests

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


# ── API helper functions ──


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


# ── Conversation API helpers ──


def api_list_conversations() -> list[dict]:
    """Fetch all conversations from backend."""
    try:
        resp = requests.get(f"{api_base}/api/conversations/", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except requests.ConnectionError:
        pass
    return []


def api_create_conversation(title: str = "新对话") -> dict | None:
    """Create a new conversation."""
    try:
        resp = requests.post(
            f"{api_base}/api/conversations/",
            json={"title": title},
            timeout=5,
        )
        if resp.status_code == 201:
            return resp.json()
    except requests.ConnectionError:
        pass
    return None


def api_get_messages(conv_id: int) -> list[dict]:
    """Fetch all messages for a conversation."""
    try:
        resp = requests.get(
            f"{api_base}/api/conversations/{conv_id}/messages",
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
    except requests.ConnectionError:
        pass
    return []


def api_add_message(conv_id: int, role: str, content: str) -> bool:
    """Add a message to a conversation."""
    try:
        resp = requests.post(
            f"{api_base}/api/conversations/{conv_id}/messages",
            json={"role": role, "content": content},
            timeout=5,
        )
        return resp.status_code == 201
    except requests.ConnectionError:
        return False


def api_rename_conversation(conv_id: int, title: str) -> bool:
    """Rename a conversation."""
    try:
        resp = requests.patch(
            f"{api_base}/api/conversations/{conv_id}",
            json={"title": title},
            timeout=5,
        )
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def api_delete_conversation(conv_id: int) -> bool:
    """Delete a conversation."""
    try:
        resp = requests.delete(
            f"{api_base}/api/conversations/{conv_id}",
            timeout=5,
        )
        return resp.status_code == 204
    except requests.ConnectionError:
        return False


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

model_name = status.get('model', 'unknown')
status_badge(f"AI助教已就绪 · {model_name}")

st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)


# ── Session state initialization ──

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "temperature" not in st.session_state:
    st.session_state.temperature = 0.7
if "active_conversation_id" not in st.session_state:
    st.session_state.active_conversation_id = None
if "conversations" not in st.session_state:
    st.session_state.conversations = []


def switch_conversation(conv_id: int):
    """Switch to a different conversation: load its messages into chat_history."""
    st.session_state.active_conversation_id = conv_id
    messages = api_get_messages(conv_id)
    st.session_state.chat_history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
    ]


def ensure_active_conversation() -> int | None:
    """Make sure there's an active conversation. Create one if needed."""
    conv_id = st.session_state.active_conversation_id

    # Validate current conv still exists
    if conv_id is not None:
        convs = st.session_state.conversations
        if not any(c["id"] == conv_id for c in convs):
            conv_id = None
            st.session_state.active_conversation_id = None

    # No active conv → pick the newest or create one
    if conv_id is None:
        convs = st.session_state.conversations
        if convs:
            conv_id = convs[0]["id"]
            switch_conversation(conv_id)
        else:
            new_conv = api_create_conversation()
            if new_conv:
                st.session_state.conversations.insert(0, new_conv)
                conv_id = new_conv["id"]
                st.session_state.active_conversation_id = conv_id
                st.session_state.chat_history = []

    return conv_id


# ── Load conversations list on first run ──

if not st.session_state.conversations and st.session_state.active_conversation_id is None:
    st.session_state.conversations = api_list_conversations()
    # Auto-select the most recent conversation
    if st.session_state.conversations:
        first = st.session_state.conversations[0]
        switch_conversation(first["id"])
    else:
        # No conversations exist, create one
        new_conv = api_create_conversation()
        if new_conv:
            st.session_state.conversations = [new_conv]
            st.session_state.active_conversation_id = new_conv["id"]
            st.session_state.chat_history = []


# ── Sidebar ──

with st.sidebar:
    # New conversation button
    if st.button("✨ 新建对话", use_container_width=True, type="primary"):
        new_conv = api_create_conversation()
        if new_conv:
            st.session_state.conversations.insert(0, new_conv)
            switch_conversation(new_conv["id"])
            st.rerun()

    glow_divider()

    # Conversation history list
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1rem;">💬 历史对话</h3>',
        unsafe_allow_html=True,
    )

    active_id = st.session_state.active_conversation_id
    convs = st.session_state.conversations

    if not convs:
        st.caption("暂无对话记录")
    else:
        for conv in convs:
            cid = conv["id"]
            title = conv.get("title", "新对话")
            is_active = cid == active_id

            # Display conversation item with button + delete
            cols = st.columns([0.85, 0.15])
            with cols[0]:
                label = f"{'▸ ' if is_active else '  '}{title}"
                btn_type = "primary" if is_active else "secondary"
                if st.button(
                    label,
                    key=f"conv_{cid}",
                    use_container_width=True,
                    type=btn_type,
                ):
                    if not is_active:
                        switch_conversation(cid)
                        st.rerun()
            with cols[1]:
                if st.button(
                    "✕",
                    key=f"del_{cid}",
                    use_container_width=True,
                ):
                    if api_delete_conversation(cid):
                        st.session_state.conversations = [
                            c for c in st.session_state.conversations if c["id"] != cid
                        ]
                        if active_id == cid:
                            # Switch to another conversation or None
                            remaining = st.session_state.conversations
                            if remaining:
                                switch_conversation(remaining[0]["id"])
                            else:
                                st.session_state.active_conversation_id = None
                                st.session_state.chat_history = []
                        st.rerun()

    glow_divider()

    # Settings
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


# ── Display chat history ──

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])


# ── Handle message sending (shared by chat_input and sidebar quick prompts) ──


def process_user_message(user_msg: str):
    """Send a user message, get AI reply, persist both to backend."""
    conv_id = ensure_active_conversation()
    if conv_id is None:
        st.error("无法创建对话，请检查后端服务是否正常运行。")
        return

    # Add user message to UI
    st.session_state.chat_history.append({"role": "user", "content": user_msg})

    # Persist user message
    api_add_message(conv_id, "user", user_msg)

    # Auto-update title from first user message
    conv = next(
        (c for c in st.session_state.conversations if c["id"] == conv_id), None
    )
    if conv and (conv.get("title") == "新对话" or len(st.session_state.chat_history) <= 2):
        new_title = user_msg[:20] + ("..." if len(user_msg) > 20 else "")
        if api_rename_conversation(conv_id, new_title):
            conv["title"] = new_title

    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_msg)

    # Get AI reply
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("AI助教正在思考..."):
            reply = send_chat(
                user_msg,
                st.session_state.chat_history[-(MAX_HISTORY + 1):-1],
            )
        st.markdown(reply)

    st.session_state.chat_history.append({"role": "assistant", "content": reply})

    # Persist AI reply
    api_add_message(conv_id, "assistant", reply)


# ── Handle pending message from sidebar ──

if "pending_message" in st.session_state:
    user_msg = st.session_state.pop("pending_message")
    process_user_message(user_msg)
    st.rerun()


# ── User input ──

user_input = st.chat_input("向AI助教提问... (例如: 解释一下B+树和B树的区别)")

if user_input:
    process_user_message(user_input)
