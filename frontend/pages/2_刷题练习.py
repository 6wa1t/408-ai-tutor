"""刷题练习页面 — 随机抽题/章节顺序、选择题/综合题、答题反馈。"""

import streamlit as st
import requests

st.set_page_config(page_title="刷题练习", page_icon="✏️", layout="wide")

api_base = st.session_state.get("api_base", "http://localhost:8000")

st.title("✏️ 刷题练习")

# ─── Sidebar ───
st.sidebar.header("练习设置")

# 1. 科目选择
subject_options = ["全部科目", "数据结构", "操作系统", "计算机组成原理", "计算机网络"]
selected_subject = st.sidebar.selectbox("选择科目", subject_options)

# 2. 题型选择
question_type_label = st.sidebar.radio(
    "题型",
    ["选择题", "综合题"],
    horizontal=True,
    key="quiz_type_select",
)
question_type_value = "choice" if question_type_label == "选择题" else "other"

# 3. 出题模式
order_mode_label = st.sidebar.radio(
    "出题模式",
    ["随机出题", "按章节顺序"],
    horizontal=True,
    key="quiz_order_mode",
)
order_mode = "random" if order_mode_label == "随机出题" else "sequential"

# ─── Session state init ───
for key, default in [
    ("quiz_questions", []),
    ("quiz_answers", {}),
    ("quiz_submitted", False),
    ("quiz_results", {}),
    ("quiz_chapters", []),
    ("quiz_chapter_idx", 0),
    ("quiz_mode", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _clean_quiz_state():
    """Reset quiz state and clean widget keys."""
    st.session_state.quiz_questions = []
    st.session_state.quiz_answers = {}
    st.session_state.quiz_submitted = False
    st.session_state.quiz_results = {}
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("q_"):
            del st.session_state[k]


def _fetch_random(subject_param, q_type, count):
    """Fetch random questions from API."""
    params = {"count": count, "question_type": q_type}
    if subject_param:
        params["subject"] = subject_param
    try:
        resp = requests.get(f"{api_base}/api/questions/random", params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("questions", [])
    except requests.ConnectionError:
        st.error("后端服务未连接")
    return []


def _fetch_chapters(subject_param, q_type):
    """Fetch chapter list for a subject."""
    if not subject_param:
        return []
    params = {"subject": subject_param, "question_type": q_type}
    try:
        resp = requests.get(f"{api_base}/api/questions/chapters", params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("chapters", [])
    except requests.ConnectionError:
        st.error("后端服务未连接")
    return []


def _fetch_chapter_questions(subject_param, chapter_name, q_type):
    """Fetch all questions for a specific chapter."""
    params = {"subject": subject_param, "chapter": chapter_name, "question_type": q_type}
    try:
        resp = requests.get(f"{api_base}/api/questions/by_chapter", params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("questions", [])
    except requests.ConnectionError:
        st.error("后端服务未连接")
    return []


# ─── Mode-specific sidebar ───

subject_param = None if selected_subject == "全部科目" else selected_subject

if order_mode == "random":
    question_count = st.sidebar.slider("题目数量", 1, 30, 10)

    # Show start button
    if st.sidebar.button("🎲 开始新一组题", type="primary"):
        _clean_quiz_state()
        questions = _fetch_random(subject_param, question_type_value, question_count)
        if questions:
            st.session_state.quiz_questions = questions
            st.session_state.quiz_mode = "random"
            st.rerun()
        elif not subject_param:
            st.sidebar.warning("随机模式下请先选择具体科目")
        else:
            st.sidebar.warning("没有找到符合条件的题目")

else:
    # Sequential mode — must select a specific subject
    if not subject_param:
        st.sidebar.warning("按章节顺序模式需要选择一个具体科目")
    else:
        # Fetch chapters (cache in session state)
        cache_key = f"_chapters_{subject_param}_{question_type_value}"
        if cache_key not in st.session_state or st.session_state.get("_chapters_subject") != cache_key:
            chapters = _fetch_chapters(subject_param, question_type_value)
            st.session_state[cache_key] = chapters
            st.session_state._chapters_subject = cache_key

        chapters = st.session_state[cache_key]

        if not chapters:
            st.sidebar.warning("该科目下没有找到符合条件的题目章节")
        else:
            # Build chapter selector options
            chapter_labels = [f"{c['name']} ({c['count']}题)" for c in chapters]
            current_idx = st.session_state.quiz_chapter_idx
            if current_idx >= len(chapters):
                current_idx = 0

            selected_chapter_label = st.sidebar.selectbox(
                "选择章节",
                chapter_labels,
                index=current_idx,
                key="chapter_selector",
            )
            # Find the index from label
            try:
                new_idx = chapter_labels.index(selected_chapter_label)
            except ValueError:
                new_idx = 0

            # Navigation buttons
            nav_col1, nav_col2 = st.sidebar.columns(2)
            with nav_col1:
                if st.button("⬅ 上一章", disabled=(new_idx <= 0)):
                    st.session_state.quiz_chapter_idx = new_idx - 1
                    st.rerun()
            with nav_col2:
                if st.button("下一章 ➡", disabled=(new_idx >= len(chapters) - 1)):
                    st.session_state.quiz_chapter_idx = new_idx + 1
                    st.rerun()

            # Load chapter button
            if st.sidebar.button("📖 加载本章题目", type="primary"):
                st.session_state.quiz_chapter_idx = new_idx
                _clean_quiz_state()
                ch_name = chapters[new_idx]["name"]
                qs = _fetch_chapter_questions(subject_param, ch_name, question_type_value)
                if qs:
                    st.session_state.quiz_questions = qs
                    st.session_state.quiz_mode = "sequential"
                    st.rerun()
                else:
                    st.sidebar.warning("该章节没有找到题目")


# ─── Main area: Info bar ───
questions = st.session_state.quiz_questions
if questions:
    mode_text = "随机出题" if st.session_state.quiz_mode == "random" else "按章节顺序"
    type_text = question_type_label
    if st.session_state.quiz_mode == "sequential" and st.session_state.quiz_chapters:
        idx = st.session_state.quiz_chapter_idx
        chs = st.session_state[st.session_state._chapters_subject]
        if idx < len(chs):
            ch_info = chs[idx]
            st.info(f"📖 {mode_text} · {type_text} · **{ch_info['name']}** · 共 {len(questions)} 题")
        else:
            st.info(f"📖 {mode_text} · {type_text} · 共 {len(questions)} 题")
    else:
        st.info(f"🎲 {mode_text} · {type_text} · 共 {len(questions)} 题")


# ─── Main area: Display questions ───

if not questions:
    st.markdown("""
    ### 暂无题目

    请在左侧设置好科目、题型和出题模式后，点击按钮开始练习。
    """)
else:
    for i, q in enumerate(questions):
        with st.container():
            st.markdown(f"---")
            st.markdown(f"**第 {i + 1} 题** | {q.get('subject', '')} · {q.get('chapter', '')} | ID: {q.get('id', '')}")
            st.markdown(q.get("question_text", ""))

            # Display options
            opt_a = q.get("option_a") or ""
            opt_b = q.get("option_b") or ""
            opt_c = q.get("option_c") or ""
            opt_d = q.get("option_d") or ""

            option_map = {}
            if opt_a: option_map["A"] = opt_a.strip()
            if opt_b: option_map["B"] = opt_b.strip()
            if opt_c: option_map["C"] = opt_c.strip()
            if opt_d: option_map["D"] = opt_d.strip()

            if option_map:
                letters = list(option_map.keys())
                display_opts = [f"{L}. {option_map[L]}" for L in letters]
                selected_display = st.radio(
                    f"选择答案 (第{i+1}题)",
                    display_opts,
                    key=f"q_{i}_{q['id']}",
                    disabled=st.session_state.quiz_submitted,
                )
                selected_letter = selected_display[0] if selected_display else ""
                st.session_state.quiz_answers[q["id"]] = selected_letter
            else:
                q_type = q.get("question_type", "essay")
                type_label = {"essay": "综合题", "fill": "填空题", "other": "综合题"}.get(q_type, q_type)
                st.caption(f"[{type_label}] 本题无选项，请在下方输入答案")
                text_ans = st.text_area(
                    f"输入答案 (第{i+1}题)",
                    key=f"q_{i}_{q['id']}",
                    height=80,
                    disabled=st.session_state.quiz_submitted,
                )
                if text_ans:
                    st.session_state.quiz_answers[q["id"]] = text_ans

            # Show result after submission
            if st.session_state.quiz_submitted and q["id"] in st.session_state.get("quiz_results", {}):
                result = st.session_state.quiz_results[q["id"]]
                correct_ans = result.get("correct_answer", "")
                user_ans = result.get("user_answer", "")
                answer_ref = result.get("answer_ref", "")
                graded = result.get("graded", True)

                if not graded:
                    # 未判分：综合题或 AI 兜底失败，仅展示参考答案/解析供用户对照
                    if result.get("analysis"):
                        st.info("⚪ 本题未自动判分（综合题/AI 未能给出答案），请对照下方参考答案自评")
                        with st.expander("📖 查看参考答案 / 解析"):
                            st.markdown(result["analysis"])
                    elif correct_ans == "(暂无答案)" and answer_ref:
                        st.warning("⚠️ 该题暂无标准答案，无法判定对错")
                        with st.expander("📖 查看原书答案"):
                            st.markdown(f"请参考: **{answer_ref}**")
                    else:
                        st.warning("⚠️ 本题未能自动判分（AI 未返回有效答案）")
                elif correct_ans == "(暂无答案)":
                    st.warning("⚠️ 该题暂无标准答案，无法判定对错")
                    if answer_ref:
                        st.caption(f"📖 答案参考: {answer_ref}")
                elif result["is_correct"]:
                    st.success(f"✅ 回答正确！正确答案: {correct_ans}")
                else:
                    st.error(
                        f"❌ 回答错误！你的答案: {user_ans}，正确答案: {correct_ans}"
                    )

                # Show analysis (from AI or database) for graded questions
                if graded and result.get("analysis"):
                    with st.expander("📖 查看解析"):
                        st.markdown(result["analysis"])


# ─── Submit all answers ───
if questions and not st.session_state.quiz_submitted:
    st.markdown("---")
    if st.button("📝 提交所有答案", type="primary"):
        if not st.session_state.quiz_answers:
            st.warning("请至少回答一道题")
        else:
            results = {}
            correct_count = 0
            graded_count = 0
            failed_count = 0
            answered_ids = [
                q["id"] for q in questions
                if q["id"] in st.session_state.quiz_answers
            ]
            total_to_submit = len(answered_ids)
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, q in enumerate(questions):
                qid = q["id"]
                user_answer = st.session_state.quiz_answers.get(qid)
                if user_answer is None:
                    continue

                status_text.text(
                    f"正在批改第 {idx + 1}/{total_to_submit} 题"
                    f"（首次作答可能需AI生成答案，请稍候）..."
                )

                try:
                    resp = requests.post(
                        f"{api_base}/api/quiz/submit",
                        json={"question_id": qid, "user_answer": user_answer},
                        timeout=60,
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        results[qid] = result
                        if result.get("graded", True):
                            graded_count += 1
                            if result["is_correct"]:
                                correct_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1

                progress_bar.progress((idx + 1) / total_to_submit)

            status_text.text("批改完成！")
            progress_bar.empty()
            status_text.empty()

            st.session_state.quiz_results = results
            st.session_state.quiz_submitted = True

            if failed_count > 0:
                st.warning(f"⚠️ 有 {failed_count} 题提交失败（网络错误或服务超时），成绩可能不准确")

            if graded_count > 0:
                accuracy = correct_count / graded_count * 100
                ungraded = total_to_submit - graded_count
                extra = f"（另有 {ungraded} 题未判分）" if ungraded > 0 else ""
                st.markdown(
                    f"### 本次成绩: {correct_count}/{graded_count} ({accuracy:.1f}%){extra}"
                )
            elif total_to_submit > 0:
                st.markdown(
                    f"### 本次共作答 {total_to_submit} 题，均未能自动判分"
                    "（综合题或 AI 未返回答案）"
                )

            st.rerun()

# Show summary if already submitted
if st.session_state.quiz_submitted and "quiz_results" in st.session_state:
    results = st.session_state.quiz_results
    graded_results = {qid: r for qid, r in results.items() if r.get("graded", True)}
    correct_count = sum(1 for r in graded_results.values() if r.get("is_correct"))
    graded_count = len(graded_results)
    ungraded_count = len(results) - graded_count
    if graded_count > 0:
        accuracy = correct_count / graded_count * 100
        extra = f"（另有 {ungraded_count} 题未判分）" if ungraded_count > 0 else ""
        st.markdown("---")
        st.markdown(
            f"### 📊 本次成绩: {correct_count}/{graded_count} ({accuracy:.1f}%){extra}"
        )

    # In sequential mode, show "next chapter" button
    if st.session_state.quiz_mode == "sequential":
        cache_key = st.session_state.get("_chapters_subject", "")
        chs = st.session_state.get(cache_key, [])
        idx = st.session_state.quiz_chapter_idx
        if chs and idx < len(chs) - 1:
            next_ch = chs[idx + 1]["name"]
            if st.button(f"➡ 进入下一章: {next_ch}", type="primary"):
                st.session_state.quiz_chapter_idx = idx + 1
                _clean_quiz_state()
                qs = _fetch_chapter_questions(
                    subject_param, next_ch, question_type_value,
                )
                if qs:
                    st.session_state.quiz_questions = qs
                    st.session_state.quiz_mode = "sequential"
                st.rerun()
