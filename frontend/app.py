"""408考研AI专属助教 — Streamlit Frontend Entry Point.

Run with:
    streamlit run frontend/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="408考研AI助教",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📚 408考研AI专属助教")

st.markdown("""
欢迎使用 **408考研AI专属助教**！

本系统帮助你高效备考408计算机综合考试，主要功能包括：

### 功能导航

- **题库导入** — 上传408题库PDF，自动解析入库
- **刷题练习** — 随机抽题、即时答题、查看解析
- **答题统计** — 查看正确率、薄弱知识点分析

### 使用流程

1. 先在左侧「题库导入」页面导入PDF题库
2. 然后到「刷题练习」开始做题
3. 最后在「答题统计」查看学习分析

---

> 后端API默认运行在 `http://localhost:8000`
> API文档: `http://localhost:8000/docs`
""")

# Sidebar config
st.sidebar.title("⚙️ 设置")
api_base = st.sidebar.text_input(
    "后端API地址",
    value="http://localhost:8000",
    key="api_base",
)
