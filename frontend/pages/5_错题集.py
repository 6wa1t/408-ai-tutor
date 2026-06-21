"""错题集页面 — 查看、管理、重做错题。"""

import sys
import pathlib
import urllib.parse
import streamlit as st
import requests

# Streamlit pages need explicit path setup to find shared/ module
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.styles import apply_theme, gradient_header, glow_divider
from shared.api import get_api_base, get_public_api_base

st.set_page_config(page_title="错题集", page_icon="📕", layout="wide")
apply_theme()

api_base = get_api_base()

gradient_header("📕 错题集", level=2)

# ── Session state init ──
for key, default in [
    ("wq_page", 1),
    ("wq_subject", "全部科目"),
    ("wq_chapter", "全部章节"),
    ("wq_status", "全部"),
    ("wq_review_mode", False),
    ("wq_review_queue", []),
    ("wq_review_data", []),
    ("wq_review_index", 0),
    ("wq_review_answered", False),
    ("wq_review_result", None),
    ("wq_review_correct_count", 0),
    ("wq_review_wrong_count", 0),
    ("wq_selected", set()),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── API helpers ──

def _get_stats():
    try:
        r = requests.get(f"{api_base}/api/wrong-questions/stats", timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.ConnectionError:
        pass
    return None


def _get_list(subject, chapter, status, page, page_size=20):
    params = {"page": page, "page_size": page_size}
    if subject and subject != "全部科目":
        params["subject"] = subject
    if chapter and chapter != "全部章节":
        params["chapter"] = chapter
    if status and status != "全部":
        status_map = {"已掌握": "correct", "待巩固": "wrong", "未重做": "unreviewed"}
        params["status"] = status_map.get(status, status)
    try:
        r = requests.get(f"{api_base}/api/wrong-questions/", params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except requests.ConnectionError:
        pass
    return None


def _get_chapters(subject):
    if not subject or subject == "全部科目":
        return []
    try:
        r = requests.get(
            f"{api_base}/api/wrong-questions/chapters",
            params={"subject": subject},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("chapters", [])
    except requests.ConnectionError:
        pass
    return []


def _remove(wrong_id):
    try:
        r = requests.delete(f"{api_base}/api/wrong-questions/{wrong_id}", timeout=10)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def _batch_remove(wrong_ids):
    try:
        r = requests.post(
            f"{api_base}/api/wrong-questions/batch-remove",
            json={"wrong_ids": wrong_ids},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("removed", 0)
    except requests.ConnectionError:
        pass
    return 0


def _get_batch_review(wrong_ids):
    try:
        r = requests.post(
            f"{api_base}/api/wrong-questions/batch-review",
            json={"wrong_ids": wrong_ids},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("items", [])
    except requests.ConnectionError:
        pass
    return []


def _submit_review(wrong_id, user_answer):
    try:
        r = requests.post(
            f"{api_base}/api/wrong-questions/{wrong_id}/review",
            json={"user_answer": user_answer},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
    except requests.ConnectionError:
        pass
    return None


def _manual_add(question_id):
    try:
        r = requests.post(
            f"{api_base}/api/wrong-questions/",
            json={"question_id": question_id},
            timeout=10,
        )
        return r.status_code == 200, r.json() if r.status_code == 200 else r.text
    except requests.ConnectionError:
        return False, "无法连接后端"


def _exit_review():
    """Clean up review session state."""
    st.session_state.wq_review_mode = False
    st.session_state.wq_review_queue = []
    st.session_state.wq_review_data = []
    st.session_state.wq_review_index = 0
    st.session_state.wq_review_answered = False
    st.session_state.wq_review_result = None
    st.session_state.wq_review_correct_count = 0
    st.session_state.wq_review_wrong_count = 0
    # Clean widget keys
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("rc_"):
            del st.session_state[k]


# ── Sidebar ──

with st.sidebar:
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1.1rem;">🔍 筛选</h3>',
        unsafe_allow_html=True,
    )

    subjects = ["全部科目", "数据结构", "操作系统", "计算机组成原理", "计算机网络"]
    selected_subject = st.selectbox("科目", subjects, key="wq_subject_select")

    chapters = _get_chapters(selected_subject)
    chapter_options = ["全部章节"] + chapters
    selected_chapter = st.selectbox("章节", chapter_options, key="wq_chapter_select")

    status_options = ["全部", "未重做", "已掌握", "待巩固"]
    selected_status = st.selectbox("状态", status_options, key="wq_status_select")

    # Prominent load button
    if st.button("📋 加载错题列表", type="primary"):
        st.session_state.wq_subject = selected_subject
        st.session_state.wq_chapter = selected_chapter
        st.session_state.wq_status = selected_status
        st.session_state.wq_page = 1
        st.session_state.wq_selected = set()
        st.rerun()

    st.divider()
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1.1rem;">⚡ 操作</h3>',
        unsafe_allow_html=True,
    )

    # Manual add
    add_id = st.number_input(
        "手动添加题目ID", min_value=1, step=1, key="wq_add_id"
    )
    if st.button("➕ 添加到错题集"):
        ok, msg = _manual_add(int(add_id))
        if ok:
            st.success("已添加到错题集")
            st.rerun()
        else:
            st.error(f"添加失败: {msg}")


# ── Stats Overview ──

stats = _get_stats()
if stats:
    total = stats.get("total", 0)
    by_status = stats.get("by_status", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("错题总数", total)
    c2.metric("未重做", by_status.get("unreviewed", 0))
    c3.metric("已掌握 ✓", by_status.get("correct", 0))
    c4.metric("待巩固 ✗", by_status.get("wrong", 0))
else:
    st.error("无法获取错题统计，请确认后端已启动")
    st.stop()


# ── Re-challenge Mode ──

if st.session_state.wq_review_mode:
    glow_divider()
    st.markdown(
        '<h3 class="gradient-text-sm" style="font-size:1.3rem;margin-bottom:12px;">'
        '🔄 重做模式</h3>',
        unsafe_allow_html=True,
    )

    queue = st.session_state.wq_review_queue
    data = st.session_state.wq_review_data
    idx = st.session_state.wq_review_index
    total_q = len(data)

    # All done
    if idx >= total_q:
        cc = st.session_state.wq_review_correct_count
        wc = st.session_state.wq_review_wrong_count
        st.markdown(
            f'<div class="score-card">'
            f'<div class="score-value">{cc}/{total_q}</div>'
            f'<p style="color:#e0e0f0;margin-top:8px;">'
            f'正确 {cc} 题，错误 {wc} 题</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("退出重做", type="primary"):
            _exit_review()
            st.rerun()
        st.stop()

    # Progress
    st.progress(idx / total_q if total_q > 0 else 0)
    st.caption(f"第 {idx + 1} / {total_q} 题")

    # Current question
    q = data[idx]
    wid = q["wrong_id"]

    st.markdown(f"**{q.get('subject', '')}** · {q.get('chapter', '')}")
    st.markdown(q.get("question_text", ""))

    # Image
    img = q.get("image_path")
    if img:
        public_base = get_public_api_base()
        for img_rel in img.split(","):
            img_rel = img_rel.strip()
            if img_rel:
                try:
                    img_col, _ = st.columns([5, 3])
                    with img_col:
                        st.image(f"{public_base}/images/{urllib.parse.quote(img_rel, safe='/')}", use_container_width=True)
                except Exception:
                    pass

    # Options
    opt_map = {}
    for letter, key in [("A", "option_a"), ("B", "option_b"),
                        ("C", "option_c"), ("D", "option_d")]:
        val = q.get(key)
        if val:
            opt_map[letter] = val.strip()

    if not st.session_state.wq_review_answered:
        # Show answer options
        if opt_map:
            letters = list(opt_map.keys())
            display_opts = [f"{L}. {opt_map[L]}" for L in letters]
            selected_display = st.radio(
                "选择答案",
                display_opts,
                key=f"rc_radio_{wid}_{idx}",
            )
            selected_letter = selected_display[0] if selected_display else ""

            if st.button("📝 提交答案", type="primary"):
                if selected_letter:
                    result = _submit_review(wid, selected_letter)
                    st.session_state.wq_review_result = result
                    st.session_state.wq_review_answered = True
                    if result and result.get("is_correct"):
                        st.session_state.wq_review_correct_count += 1
                    else:
                        st.session_state.wq_review_wrong_count += 1
                    st.rerun()
                else:
                    st.warning("请选择一个答案")
        else:
            # Non-choice question
            text_ans = st.text_area("输入答案", key=f"rc_text_{wid}_{idx}")
            if st.button("📝 提交答案", type="primary"):
                if text_ans:
                    result = _submit_review(wid, text_ans)
                    st.session_state.wq_review_result = result
                    st.session_state.wq_review_answered = True
                    if result and result.get("is_correct"):
                        st.session_state.wq_review_correct_count += 1
                    else:
                        st.session_state.wq_review_wrong_count += 1
                    st.rerun()
    else:
        # Show result
        result = st.session_state.wq_review_result
        if result:
            if result.get("is_correct"):
                st.success(f"✅ 回答正确！正确答案: {result.get('correct_answer', '')}")
            else:
                st.error(
                    f"❌ 回答错误！你的答案: {result.get('user_answer', '')}，"
                    f"正确答案: {result.get('correct_answer', '')}"
                )
            if result.get("analysis"):
                with st.expander("📖 查看解析"):
                    st.markdown(result["analysis"])

        # Navigation
        col1, col2 = st.columns(2)
        with col1:
            if st.button("下一题 →", type="primary"):
                st.session_state.wq_review_index += 1
                st.session_state.wq_review_answered = False
                st.session_state.wq_review_result = None
                st.rerun()
        with col2:
            if st.button("退出重做"):
                _exit_review()
                st.rerun()

    st.stop()


# ── Main: Question List ──

glow_divider()

# Batch action bar
sel = st.session_state.wq_selected
if sel:
    action_col1, action_col2, action_col3 = st.columns([1, 1, 3])
    with action_col1:
        if st.button(f"🔄 重做选中 ({len(sel)})", type="primary"):
            wrong_ids = list(sel)
            items = _get_batch_review(wrong_ids)
            if items:
                st.session_state.wq_review_mode = True
                st.session_state.wq_review_queue = wrong_ids
                st.session_state.wq_review_data = items
                st.session_state.wq_review_index = 0
                st.session_state.wq_review_answered = False
                st.session_state.wq_review_result = None
                st.session_state.wq_review_correct_count = 0
                st.session_state.wq_review_wrong_count = 0
                st.rerun()
            else:
                st.warning("无法加载题目数据")
    with action_col2:
        if st.button(f"🗑️ 移除选中 ({len(sel)})"):
            count = _batch_remove(list(sel))
            st.session_state.wq_selected = set()
            st.success(f"已移除 {count} 题")
            st.rerun()

# Fetch list
result = _get_list(
    st.session_state.wq_subject,
    st.session_state.wq_chapter,
    st.session_state.wq_status,
    st.session_state.wq_page,
)

if not result:
    st.info("暂无错题数据")
    st.stop()

items = result.get("items", [])
total = result.get("total", 0)
pages = result.get("pages", 1)
current_page = result.get("page", 1)

if not items:
    st.markdown(
        '<div class="neon-card" style="text-align:center;padding:40px;">'
        '<p style="color:#7878a0;font-size:1.1rem;">🎉 暂无错题</p>'
        '<p style="color:#7878a0;">刷题答错后会自动收录到这里</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.caption(f"共 {total} 题 · 第 {current_page}/{pages} 页")

# Render each item
status_icon = {"correct": "🟢", "wrong": "🔴", "unreviewed": "⚪"}
status_class = {"correct": "wq-correct", "wrong": "wq-wrong", "unreviewed": "wq-unreviewed"}
dot_class = {"correct": "wq-dot-correct", "wrong": "wq-dot-wrong", "unreviewed": "wq-dot-unreviewed"}

for item in items:
    wid = item["id"]
    ls = item.get("last_status", "unreviewed")
    cls = status_class.get(ls, "wq-unreviewed")
    dcls = dot_class.get(ls, "wq-dot-unreviewed")
    subject = item.get("subject", "")
    chapter = item.get("chapter", "")
    preview = item.get("question_text_preview", "")
    reviews = item.get("review_count", 0)

    # Checkbox for selection
    checked = st.checkbox(
        "select",
        key=f"wq_chk_{wid}",
        value=(wid in st.session_state.wq_selected),
        label_visibility="collapsed",
    )
    if checked:
        st.session_state.wq_selected.add(wid)
    else:
        st.session_state.wq_selected.discard(wid)

    # Card HTML
    st.markdown(
        f'<div class="wq-item {cls}" style="margin-left:36px;">'
        f'<span class="wq-status-dot {dcls}"></span>'
        f'<span class="wq-subject-tag">{subject}</span>'
        f'<span style="color:#7878a0;font-size:0.85rem;">{chapter}</span>'
        f'<p style="color:#e0e0f0;margin:8px 0 4px 0;">{preview}</p>'
        f'<span style="color:#7878a0;font-size:0.8rem;">'
        f'重做 {reviews} 次 · '
        f'{"已掌握" if ls == "correct" else ("待巩固" if ls == "wrong" else "未重做")}'
        f'</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Action buttons
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 6])
    with btn_col1:
        if st.button("🔄 重做", key=f"wq_do_{wid}"):
            items_data = _get_batch_review([wid])
            if items_data:
                st.session_state.wq_review_mode = True
                st.session_state.wq_review_queue = [wid]
                st.session_state.wq_review_data = items_data
                st.session_state.wq_review_index = 0
                st.session_state.wq_review_answered = False
                st.session_state.wq_review_result = None
                st.session_state.wq_review_correct_count = 0
                st.session_state.wq_review_wrong_count = 0
                st.rerun()
    with btn_col2:
        if st.button("🗑️ 移除", key=f"wq_rm_{wid}"):
            if _remove(wid):
                st.session_state.wq_selected.discard(wid)
                st.rerun()

# ── Pagination ──
if pages > 1:
    st.markdown("---")
    pg_col1, pg_col2, pg_col3 = st.columns([1, 2, 1])
    with pg_col1:
        if st.button("← 上一页", disabled=(current_page <= 1)):
            st.session_state.wq_page = current_page - 1
            st.rerun()
    with pg_col2:
        st.markdown(
            f'<p style="text-align:center;color:#7878a0;">'
            f'第 {current_page} / {pages} 页</p>',
            unsafe_allow_html=True,
        )
    with pg_col3:
        if st.button("下一页 →", disabled=(current_page >= pages)):
            st.session_state.wq_page = current_page + 1
            st.rerun()
