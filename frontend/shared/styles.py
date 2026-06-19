"""408考研AI助教 — 暗黑炫酷主题样式模块。

每个页面导入后调用 apply_theme() 注入全局CSS。
"""
import streamlit as st


CYBERPUNK_CSS = """
/* ═══════════════════════════════════════════
   408 AI Tutor — Cyberpunk Dark Theme
   ═══════════════════════════════════════════ */

/* ── CSS Variables ── */
:root {
    --neon-cyan: #00f0ff;
    --neon-magenta: #ff00e5;
    --neon-purple: #a855f7;
    --neon-green: #22d3ee;
    --bg-deep: #0a0a1a;
    --bg-card: #0f0f24;
    --bg-surface: #16163a;
    --bg-hover: #1e1e4a;
    --text-primary: #e0e0f0;
    --text-muted: #7878a0;
    --border-subtle: rgba(0, 240, 255, 0.12);
    --border-glow: rgba(0, 240, 255, 0.35);
    --glow-cyan: 0 0 8px rgba(0, 240, 255, 0.3), 0 0 20px rgba(0, 240, 255, 0.1);
    --glow-purple: 0 0 8px rgba(168, 85, 247, 0.3), 0 0 20px rgba(168, 85, 247, 0.1);
    --glow-magenta: 0 0 8px rgba(255, 0, 229, 0.3), 0 0 20px rgba(255, 0, 229, 0.1);
    --radius: 10px;
    --radius-lg: 16px;
}

/* ── Animated Background ── */
.stApp {
    background: linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 50%, #0a0a1a 100%);
}

.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(ellipse at 20% 50%, rgba(0, 240, 255, 0.03) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 20%, rgba(168, 85, 247, 0.03) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 80%, rgba(255, 0, 229, 0.02) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
}

/* ── Scrollbar ── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: var(--bg-deep);
}
::-webkit-scrollbar-thumb {
    background: rgba(0, 240, 255, 0.25);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 240, 255, 0.5);
}

/* ── Gradient Text Headers ── */
.gradient-text {
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple), var(--neon-magenta));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 800;
    letter-spacing: -0.02em;
}

.gradient-text-sm {
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 700;
}

/* ── Neon Card ── */
.neon-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}
.neon-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple), var(--neon-magenta));
    opacity: 0.6;
}
.neon-card:hover {
    border-color: var(--border-glow);
    box-shadow: var(--glow-cyan);
    transform: translateY(-2px);
}

/* ── Neon Card Variants ── */
.neon-card-cyan {
    background: var(--bg-card);
    border: 1px solid rgba(0, 240, 255, 0.2);
    border-radius: var(--radius-lg);
    padding: 24px;
}
.neon-card-cyan:hover {
    box-shadow: var(--glow-cyan);
}
.neon-card-purple {
    background: var(--bg-card);
    border: 1px solid rgba(168, 85, 247, 0.2);
    border-radius: var(--radius-lg);
    padding: 24px;
}
.neon-card-purple:hover {
    box-shadow: var(--glow-purple);
}
.neon-card-magenta {
    background: var(--bg-card);
    border: 1px solid rgba(255, 0, 229, 0.2);
    border-radius: var(--radius-lg);
    padding: 24px;
}
.neon-card-magenta:hover {
    box-shadow: var(--glow-magenta);
}

/* ── Buttons ── */
.stButton > button {
    border-radius: var(--radius) !important;
    font-weight: 600 !important;
    transition: all 0.25s ease !important;
    letter-spacing: 0.02em;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
}

/* Primary buttons — neon gradient */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stFormSubmitButton"] {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(168, 85, 247, 0.15)) !important;
    border: 1px solid var(--neon-cyan) !important;
    color: var(--neon-cyan) !important;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.2) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.25), rgba(168, 85, 247, 0.25)) !important;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.4), 0 0 40px rgba(0, 240, 255, 0.15) !important;
}

/* ── Metric Cards ── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px 20px !important;
    position: relative;
    overflow: hidden;
}
[data-testid="stMetric"]::after {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, var(--neon-cyan), var(--neon-purple));
    border-radius: 0 2px 2px 0;
}
[data-testid="stMetricValue"] {
    color: var(--neon-cyan) !important;
    font-weight: 700 !important;
}
[data-testid="stMetricLabel"] {
    color: var(--text-muted) !important;
    font-size: 0.85rem !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) var(--radius) 0 0 !important;
    color: var(--text-muted) !important;
    padding: 10px 24px !important;
    font-weight: 600 !important;
    transition: all 0.25s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--text-primary) !important;
    border-color: var(--border-glow) !important;
    background: var(--bg-surface) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--neon-cyan) !important;
    border-color: var(--neon-cyan) !important;
    border-bottom-color: transparent !important;
    background: var(--bg-surface) !important;
    box-shadow: 0 -2px 8px rgba(0, 240, 255, 0.15) !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple)) !important;
    height: 3px !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border-subtle) !important;
}
section[data-testid="stSidebar"]::after {
    content: '';
    position: absolute;
    right: 0; top: 0; bottom: 0;
    width: 1px;
    background: linear-gradient(180deg, var(--neon-cyan), var(--neon-purple), var(--neon-magenta));
    opacity: 0.3;
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--neon-cyan) !important;
}

/* ── Radio Buttons ── */
.stRadio > div[role="radiogroup"] > label {
    border-radius: var(--radius) !important;
    padding: 6px 14px !important;
    transition: all 0.2s ease !important;
}
.stRadio > div[role="radiogroup"] > label:hover {
    background: var(--bg-hover) !important;
}
.stRadio > div[role="radiogroup"] > label[data-baseweb="radio"]:has(input:checked) {
    background: rgba(0, 240, 255, 0.08) !important;
    border: 1px solid rgba(0, 240, 255, 0.3);
}
.stRadio > div[role="radiogroup"] > label > div:first-child {
    border-color: var(--text-muted) !important;
}
.stRadio > div[role="radiogroup"] > label:has(input:checked) > div:first-child {
    border-color: var(--neon-cyan) !important;
    background: var(--neon-cyan) !important;
}

/* ── Select / Dropdown ── */
.stSelectbox > div > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
}
.stSelectbox > div > div:hover {
    border-color: var(--border-glow) !important;
}

/* ── Text Input ── */
.stTextInput > div > div > input {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
}
.stTextInput > div > div > input:focus {
    border-color: var(--neon-cyan) !important;
    box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.15) !important;
}

/* ── Text Area ── */
.stTextArea > div > div > textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
}
.stTextArea > div > div > textarea:focus {
    border-color: var(--neon-cyan) !important;
    box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.15) !important;
}

/* ── Slider ── */
.stSlider > div > div > div > div {
    color: var(--neon-cyan) !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    border-radius: var(--radius) !important;
    transition: all 0.2s ease !important;
}
.streamlit-expanderHeader:hover {
    background: var(--bg-hover) !important;
    color: var(--neon-cyan) !important;
}
.streamlit-expanderContent {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 0 0 var(--radius) var(--radius) !important;
}

/* ── Progress Bar — Neon Gradient ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple), var(--neon-magenta)) !important;
    border-radius: 4px !important;
    box-shadow: 0 0 8px rgba(0, 240, 255, 0.4) !important;
}

/* ── Alert Boxes ── */
.stAlert {
    border-radius: var(--radius) !important;
    border: 1px solid transparent !important;
    background: var(--bg-card) !important;
}
div[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
}

/* Success — neon green border */
div[data-baseweb="notification"][data-testid*="stAlert"] > div:first-child {
    background: rgba(34, 211, 238, 0.06) !important;
}

/* ── Chat Bubbles ── */
.stChatMessage {
    border-radius: var(--radius-lg) !important;
    border: 1px solid var(--border-subtle) !important;
}
/* User messages — cyan tint */
div[data-testid="chatAvatarContainer"]:has(img) ~ .stChatMessage,
.stChatMessage:has([data-testid="chatAvatarUser"]) {
    background: rgba(0, 240, 255, 0.04) !important;
    border-color: rgba(0, 240, 255, 0.15) !important;
}

/* ── Chat Input ── */
.stChatInput > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
}
.stChatInput > div:focus-within {
    border-color: var(--neon-cyan) !important;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.2) !important;
}

/* ── File Uploader ── */
[data-testid="stFileUploader"] {
    border: 2px dashed rgba(0, 240, 255, 0.25) !important;
    border-radius: var(--radius-lg) !important;
    background: rgba(0, 240, 255, 0.02) !important;
    padding: 20px !important;
    transition: all 0.3s ease !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--neon-cyan) !important;
    background: rgba(0, 240, 255, 0.05) !important;
    box-shadow: var(--glow-cyan) !important;
}

/* ── Code Blocks ── */
.stCodeBlock,
code {
    background: rgba(0, 240, 255, 0.06) !important;
    border: 1px solid rgba(0, 240, 255, 0.1) !important;
    border-radius: 6px !important;
    color: var(--neon-cyan) !important;
}

/* ── Dividers ── */
.neon-divider {
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--neon-cyan), var(--neon-purple), var(--neon-magenta), transparent);
    border: none;
    margin: 24px 0;
    opacity: 0.5;
    border-radius: 1px;
}

/* ── Question Card ── */
.question-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 24px;
    margin-bottom: 20px;
    position: relative;
    transition: all 0.2s ease;
}
.question-card::before {
    content: '';
    position: absolute;
    left: 0; top: 16px; bottom: 16px;
    width: 3px;
    background: linear-gradient(180deg, var(--neon-cyan), var(--neon-purple));
    border-radius: 0 2px 2px 0;
}
.question-card:hover {
    border-color: var(--border-glow);
    box-shadow: var(--glow-cyan);
}

/* ── Score Card ── */
.score-card {
    background: var(--bg-card);
    border: 1px solid var(--neon-cyan);
    border-radius: var(--radius-lg);
    padding: 28px;
    text-align: center;
    box-shadow: var(--glow-cyan);
    animation: scorePulse 2s ease-in-out infinite;
}
@keyframes scorePulse {
    0%, 100% { box-shadow: 0 0 8px rgba(0, 240, 255, 0.3); }
    50% { box-shadow: 0 0 20px rgba(0, 240, 255, 0.5), 0 0 40px rgba(0, 240, 255, 0.2); }
}
.score-value {
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

/* ── Status Badge ── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(0, 240, 255, 0.08);
    border: 1px solid rgba(0, 240, 255, 0.3);
    border-radius: 20px;
    padding: 8px 20px;
    color: var(--neon-cyan);
    font-weight: 600;
    font-size: 0.9rem;
}
.status-badge::before {
    content: '';
    width: 8px; height: 8px;
    background: var(--neon-cyan);
    border-radius: 50%;
    animation: badgePulse 1.5s ease-in-out infinite;
}
@keyframes badgePulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--neon-cyan); }
    50% { opacity: 0.5; box-shadow: 0 0 8px var(--neon-cyan); }
}

/* ── Weak Knowledge Bars ── */
.weak-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border-radius: var(--radius);
    margin-bottom: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    transition: all 0.2s ease;
}
.weak-item:hover {
    border-color: var(--border-glow);
}
.weak-red { border-left: 3px solid #ef4444; }
.weak-yellow { border-left: 3px solid #f59e0b; }
.weak-green { border-left: 3px solid var(--neon-green); }

/* ── History Row ── */
.history-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 16px;
    border-radius: var(--radius);
    margin-bottom: 4px;
    transition: background 0.2s ease;
}
.history-row:nth-child(odd) {
    background: rgba(0, 240, 255, 0.03);
}
.history-row:hover {
    background: var(--bg-hover);
}

/* ── Tagline ── */
.tagline {
    color: var(--text-muted);
    font-size: 1.1rem;
    margin-top: -8px;
    margin-bottom: 32px;
    font-weight: 400;
}

/* ── Upload Zone ── */
.upload-zone {
    border: 2px dashed rgba(0, 240, 255, 0.2);
    border-radius: var(--radius-lg);
    padding: 24px;
    background: rgba(0, 240, 255, 0.02);
    transition: all 0.3s ease;
}
.upload-zone:hover {
    border-color: var(--neon-cyan);
    box-shadow: var(--glow-cyan);
}

/* ── Hide Streamlit Footer / Menu ── */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background: transparent !important;
}

/* ── Image styling ── */
.stImage > img {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border-subtle) !important;
}

/* ── Caption styling ── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--text-muted) !important;
}

/* ── Wrong Question List Items ── */
.wq-item {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 14px 18px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
    position: relative;
}
.wq-item:hover {
    border-color: var(--border-glow);
    box-shadow: var(--glow-cyan);
}
.wq-correct {
    border-left: 3px solid #00ff88 !important;
}
.wq-wrong {
    border-left: 3px solid #ff4444 !important;
}
.wq-unreviewed {
    border-left: 3px solid #555577 !important;
}
.wq-status-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
}
.wq-dot-correct { background: #00ff88; box-shadow: 0 0 6px #00ff8866; }
.wq-dot-wrong { background: #ff4444; box-shadow: 0 0 6px #ff444466; }
.wq-dot-unreviewed { background: #555577; }
.wq-subject-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 8px;
    background: rgba(0, 240, 255, 0.1);
    color: var(--neon-cyan);
    border: 1px solid rgba(0, 240, 255, 0.2);
}
.wq-review-card {
    background: var(--bg-card);
    border: 1px solid var(--neon-cyan);
    border-radius: var(--radius-lg);
    padding: 28px;
    box-shadow: var(--glow-cyan);
}
"""


def apply_theme():
    """注入暗黑炫酷主题CSS到当前页面。
    
    使用 st.html() 而非 st.markdown()，因为 Streamlit >= 1.38
    会把 <style> 内的CSS文本同时渲染为可见文字。
    st.html() 直接注入原始HTML，不会显示文本。
    """
    st.html(f"<style>{CYBERPUNK_CSS}</style>")


def gradient_header(text: str, level: int = 1):
    """渲染霓虹渐变标题。"""
    tag = f"h{level}"
    size = {1: "2.8rem", 2: "2rem", 3: "1.5rem"}.get(level, "1.5rem")
    st.markdown(
        f'<{tag} class="gradient-text" style="font-size:{size};margin-bottom:0.5rem;">'
        f'{text}</{tag}>',
        unsafe_allow_html=True,
    )


def neon_card(title: str, content: str, variant: str = ""):
    """渲染霓虹发光卡片。"""
    cls = f"neon-card-{variant}" if variant else "neon-card"
    st.markdown(
        f'<div class="{cls}">'
        f'<h3 style="color:#00f0ff;margin:0 0 8px 0;font-size:1.1rem;">{title}</h3>'
        f'<p style="color:#e0e0f0;margin:0;line-height:1.6;">{content}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def glow_divider():
    """渲染霓虹发光分割线。"""
    st.markdown('<div class="neon-divider"></div>', unsafe_allow_html=True)


def status_badge(text: str):
    """渲染脉冲状态徽章。"""
    st.markdown(
        f'<div class="status-badge">{text}</div>',
        unsafe_allow_html=True,
    )
