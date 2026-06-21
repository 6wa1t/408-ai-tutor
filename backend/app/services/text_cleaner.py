"""题目文本清洗 — 在写入数据库前格式化题目文本。

清洗步骤:
1. 检测 C 语言函数代码段（花括号深度计数），包裹为 ```c 代码围栏
2. 子问题编号前添加段落分隔
3. 非代码区域的 \\n 替换为 <br>（保留代码块内换行）
4. 清理常见 PDF 扫描多余字符

所有导入流程（API 上传 / CLI 脚本）和存量数据清洗均调用此模块，
保证数据库中 question_text 已经是可直接渲染的格式。
"""

import re


# ── C 函数代码块检测 ──

_CODE_START_RE = re.compile(
    r'^(int|float|void|unsigned|char|double|long)\s+\w+\s*\('
)


def _detect_code_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """返回 [(start_idx, end_idx), ...] 表示代码块的行范围（含两端）。"""
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if _CODE_START_RE.match(stripped):
            start = i
            depth = stripped.count('{') - stripped.count('}')
            if depth > 0 or '{' not in stripped:
                # 多行函数，向下寻找匹配的 }
                for j in range(i + 1, len(lines)):
                    depth += lines[j].count('{') - lines[j].count('}')
                    if depth <= 0:
                        blocks.append((start, j))
                        i = j + 1
                        break
                else:
                    # 未找到匹配的 }，跳过
                    i += 1
                continue
            else:
                # 单行函数（极少见）
                blocks.append((start, start))
                i += 1
                continue
        i += 1
    return blocks


# ── PDF 扫描多余字符清理 ──

# 装饰性重复符号行（如 ⏟⏟⏟、‾‾‾、___）
_DECORATIVE_LINE_RE = re.compile(r'^[⏟⏞⎵⎴‾_~\-=]{3,}$')
# 多余空行合并
_MULTI_BR_RE = re.compile(r'(<br\s*/?>\s*){3,}')


def _clean_pdf_artifacts(text: str) -> str:
    """清理常见 PDF 扫描产生的多余字符。"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if _DECORATIVE_LINE_RE.match(line.strip()):
            continue  # 跳过装饰性符号行
        cleaned.append(line)
    return '\n'.join(cleaned)


# ── 子问题间距 ──

_SUB_Q_RE = re.compile(r'\n([（(][1-9]\d*[）)])')


# ── 主清洗函数 ──


def clean_question_text(text: str) -> str:
    """清洗题目文本，返回可直接由 st.markdown() 渲染的格式。

    处理流程:
    1. 清理 PDF 扫描多余字符
    2. 检测 C 代码块并包裹为 ```c 围栏
    3. 子问题编号前加段落分隔（\\n\\n\\n）
    4. 非代码区 \\n → <br>；代码区保留 \\n
    """
    if not text:
        return text

    # ── Step 1: PDF 扫描清理 ──
    text = _clean_pdf_artifacts(text)

    # ── Step 2: 检测 C 代码块行范围 ──
    lines = text.split('\n')
    code_blocks = _detect_code_blocks(lines)

    # ── Step 3: 子问题间距（在原始 \\n 上操作）──
    text = '\n'.join(lines)
    text = _SUB_Q_RE.sub(r'\n\n\n\1', text)
    lines = text.split('\n')

    # ── Step 4: 分区处理 — 代码块保留 \\n，其余 \\n → <br> ──
    # 构建行索引集合，标记哪些行属于代码块
    code_line_indices: set[int] = set()
    for start, end in code_blocks:
        for idx in range(start, end + 1):
            code_line_indices.add(idx)

    sections: list[str] = []
    current: list[str] = []
    in_code = False
    fence_positions: list[int] = []  # 记录代码围栏插入位置

    for i, line in enumerate(lines):
        is_code_line = i in code_line_indices

        if is_code_line and not in_code:
            # 进入代码块：先输出之前积累的非代码行
            if current:
                sections.append('<br>'.join(current))
                current = []
            in_code = True
            sections.append('```c\n')

        if not is_code_line and in_code:
            # 离开代码块
            sections.append('\n'.join(current) if current else '')
            current = []
            sections.append('\n```\n')
            in_code = False

        if not is_code_line and not in_code:
            current.append(line)
        elif is_code_line:
            current.append(line)

    # 处理尾部
    if in_code:
        sections.append('\n'.join(current) if current else '')
        sections.append('\n```\n')
    elif current:
        sections.append('<br>'.join(current))

    return ''.join(sections)


def clean_question_fields(data: dict) -> dict:
    """清洗题目的所有文本字段，返回新 dict。

    data 应包含 question_text, option_a~d, analysis 等键。
    只清洗非 None 的文本字段。
    """
    text_fields = ['question_text', 'option_a', 'option_b',
                   'option_c', 'option_d', 'analysis']
    result = dict(data)
    for field in text_fields:
        val = result.get(field)
        if val and isinstance(val, str):
            result[field] = clean_question_text(val)
    return result
