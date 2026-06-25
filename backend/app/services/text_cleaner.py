"""题目文本清洗 — 在写入数据库前格式化题目文本。

清洗步骤:
0.  还原已有 <br> 标签为 \\n（幂等性）
0.5 修复 PUA 私用区字符（PDF 自定义字体编码 → 标准 Unicode）
1.  清理 PDF 扫描装饰性符号行
1.5 移除尾部 footer 残留（公众号、页码、水印、章节标题）
2.  检测 C/C++ 代码块（花括号深度计数）
2.5 检测汇编代码块（连续汇编指令行）
3.  子问题编号前添加段落分隔
4.  非代码区 \\n → 行尾双空格换行；代码区保留 \\n
5.  非代码区行内汇编关键词用 `反引号` 标记

所有导入流程（API 上传 / CLI 脚本）和存量数据清洗均调用此模块，
保证数据库中 question_text 已经是可直接渲染的格式。
"""

import re


# ── PUA 私用区字符修复 ──────────────────────────
# PDF 使用 PMExtra 自定义字体编码数学符号，存储在 Unicode 私用区 (U+F0xx)
# 此映射表将其替换为标准 Unicode

_PUA_PAIRED_REPLACEMENTS = [
    ('\uf0ee', '(', ')'),         # 圆括号: O(n²)
    ('\uf0f6', '[', ']'),         # 方括号: A[0..n]
    ('\uf0f4', '|', '|'),         # 绝对值: |V| > |E|
    ('\uf0f7', '\u230a', '\u230b'),  # 下取整: ⌊x⌋
    ('\uf0f8', '\u2308', '\u2309'),  # 上取整: ⌈x⌉
]

_PUA_SINGLE_REPLACEMENTS = {
    '\uf0e0': '',                 # ⟨ 冗余左尖括号
    '\uf0e1': '',                 # 分隔符（冗余）
    '\uf0e2': '',                 # ⟩ 冗余右尖括号
    '\uf00a': "'",                # ′ 上标/撇号
    '\uf0e8': '\u23a7',           # ⎧ 左花括号上段
    '\uf0e9': '\u23ab',           # ⎫ 右花括号上段
    '\uf0ea': '\u23aa',           # ⎪ 花括号延伸
    '\uf0e3': '\u23a7',           # ⎧ 分段函数左括号
    '\uf0e4': '\u222a',           # ∪ 并集
    '\uf0b1': '\u2211',           # ∑ 求和符号
    '\uf0dc': '\u0305',           # ̅ 组合上划线(布尔补)
    '\uf0fb': '\u23df',           # ⏟ 下花括号
    '\uf0fc': '\u23df',
    '\uf0fd': '\u23df',
}

_PUA_RE = re.compile(r'[\ue000-\uf8ff]')


def _repair_pua(text: str) -> str:
    """将 PUA 私用区字符替换为标准 Unicode。"""
    if not text or not _PUA_RE.search(text):
        return text
    # 配对括号修复
    for pua_ch, open_ch, close_ch in _PUA_PAIRED_REPLACEMENTS:
        pattern = re.escape(pua_ch) + r'\s+' + re.escape(pua_ch)
        text = re.sub(pattern, open_ch + close_ch, text)
        text = text.replace(pua_ch, open_ch)
    # 单字符替换
    for pua_ch, replacement in _PUA_SINGLE_REPLACEMENTS.items():
        text = text.replace(pua_ch, replacement)
    # 兜底：移除残余 PUA 字符
    text = _PUA_RE.sub('', text)
    return text


def repair_pua_text(text: str) -> str:
    """公开接口，供 import_service 等外部模块调用。"""
    return _repair_pua(text)


# ── C/C++ 代码块检测 ──

_CODE_START_RE = re.compile(
    r'^(int|float|void|unsigned|char|double|long|short|'
    r'typedef|struct|#include|#define|static|extern|'
    r'size_t|bool|auto|const|register|volatile)\b'
)

# 注释行也属于代码块的一部分
_COMMENT_LINE_RE = re.compile(r'^\s*(//|/\*|\*)')


def _detect_code_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """返回 [(start_idx, end_idx), ...] 表示 C/C++ 代码块的行范围（含两端）。"""
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if _CODE_START_RE.match(stripped):
            start = i
            # 花括号深度计数
            depth = stripped.count('{') - stripped.count('}')
            if depth > 0 or '{' not in stripped:
                # 多行函数/结构体，向下寻找匹配的 }
                for j in range(i + 1, len(lines)):
                    depth += lines[j].count('{') - lines[j].count('}')
                    if depth <= 0:
                        blocks.append((start, j))
                        i = j + 1
                        break
                else:
                    # 未找到匹配的 }，但起始行确实是代码，尽量包含到 } 或连续代码行
                    end = start
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if s and ('{' in s or '}' in s or ';' in s or
                                  _COMMENT_LINE_RE.match(s) or
                                  re.match(r'^\s*\w', s)):
                            end = j
                            if '}' in s and depth <= 0:
                                break
                        elif not s:
                            break
                        else:
                            break
                    blocks.append((start, end))
                    i = end + 1
                continue
            else:
                # 单行函数
                blocks.append((start, start))
                i += 1
                continue
        i += 1
    return blocks


# ── 汇编代码块检测 ──

# x86 指令集关键词
_X86_MNEMONICS = {
    'push', 'pop', 'mov', 'movzx', 'movsx', 'lea',
    'add', 'adc', 'sub', 'sbb', 'imul', 'mul', 'idiv', 'div',
    'inc', 'dec', 'neg', 'not',
    'and', 'or', 'xor', 'test',
    'shl', 'shr', 'sar', 'sal', 'rol', 'ror',
    'cmp', 'jmp', 'je', 'jne', 'jz', 'jnz', 'jle', 'jge', 'jl', 'jg',
    'ja', 'jae', 'jb', 'jbe', 'jc', 'jnc', 'jo', 'jno', 'js', 'jns',
    'call', 'ret', 'nop', 'int',
    'cdq', 'cwd', 'cbw', 'cwde', 'cdqe',
    'xchg', 'bswap', 'movabs',
    'cmovz', 'cmovnz', 'cmovl', 'cmovg', 'cmovle', 'cmovge',
    'setz', 'setnz', 'setl', 'setg', 'setle', 'setge',
}

# RISC-V 指令集关键词
_RISCV_MNEMONICS = {
    'add', 'addi', 'sub', 'and', 'andi', 'or', 'ori', 'xor', 'xori',
    'sll', 'slli', 'srl', 'srli', 'sra', 'srai',
    'slt', 'slti', 'sltu', 'sltiu',
    'lw', 'lh', 'lhu', 'lb', 'lbu', 'sw', 'sh', 'sb',
    'beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu',
    'j', 'jal', 'jalr', 'lui', 'auipc',
    'ecall', 'ebreak', 'fence',
    'mul', 'mulh', 'div', 'divu', 'rem', 'remu',
}

_ALL_ASM_MNEMONICS = _X86_MNEMONICS | _RISCV_MNEMONICS

# 匹配一行以汇编指令开头（可选前导行号/地址）
_ASM_LINE_RE = re.compile(
    r'^(\s*\d+\s+[0-9a-fA-F]+\s+)?'  # 可选的行号和地址
    r'(' + '|'.join(sorted(_ALL_ASM_MNEMONICS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)

# 行内汇编关键词（用于在非代码区域标记）
_INLINE_ASM_KEYWORDS = sorted(
    _X86_MNEMONICS - {'int', 'and', 'or', 'not'},  # 排除常见英文词
    key=len, reverse=True
)
_INLINE_ASM_RE = re.compile(
    r'(?<!`)\b(' + '|'.join(_INLINE_ASM_KEYWORDS) + r')\b(?!`)',
    re.IGNORECASE
)


def _detect_assembly_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """检测连续的汇编指令行，返回 [(start, end), ...]。"""
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if _ASM_LINE_RE.match(lines[i].strip()):
            start = i
            # 向下扩展，找到连续的汇编行
            j = i + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:
                    # 空行：如果后面还有汇编行则包含
                    if j + 1 < len(lines) and _ASM_LINE_RE.match(lines[j + 1].strip()):
                        j += 1
                        continue
                    break
                if _ASM_LINE_RE.match(stripped):
                    j += 1
                else:
                    break
            end = j - 1
            if end - start >= 1:  # 至少连续 2 行
                blocks.append((start, end))
            i = end + 1
        else:
            i += 1
    return blocks


def _mark_inline_asm(text: str) -> str:
    """在非代码区域标记行内汇编关键词。"""
    # 只处理不在代码围栏内的文本
    # 先找到所有 ``` 围栏位置，跳过围栏内的文本
    parts = re.split(r'(```[\s\S]*?```)', text)
    result = []
    for part in parts:
        if part.startswith('```'):
            # 代码围栏内，不处理
            result.append(part)
        else:
            # 非代码区域，标记汇编关键词
            result.append(_INLINE_ASM_RE.sub(r'`\1`', part))
    return ''.join(result)


# ── PDF 扫描多余字符清理 ──

_DECORATIVE_LINE_RE = re.compile(r'^[⏟⏞⎵⎴‾_~\-=]{3,}$')


def _clean_pdf_artifacts(text: str) -> str:
    """清理常见 PDF 扫描产生的多余字符。"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if _DECORATIVE_LINE_RE.match(line.strip()):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


# ── Footer 清理 ──

_FOOTER_PATTERNS = [
    re.compile(r'公众号[：:]\s*做题本(?:最TOP|集结地).*'),
    re.compile(r'做题本(?:最TOP|集结地)[^\n]*'),
    re.compile(r'WD[·].+?[·]\s*\d+\..+?'),
    re.compile(r'王道.+?[·].+?[·]\s*\d+\..+?'),
    re.compile(r'王道.+?课后习题[·].+?'),
    re.compile(r'王道.+?选择篇[·].+?'),
    re.compile(r'王道\S+[·][^\n]+'),
    re.compile(r'[·]?\s*第\s*\d+\s*页[，,]\s*共\s*\d+\s*页\s*[·]?'),
    re.compile(r'所有题本[：:]\s*\S+'),
    re.compile(r'https?://\S+题本\S*'),
]

# 章节标题行（出现在题目末尾时移除）
_CHAPTER_TITLE_RE = re.compile(
    r'^(第\s*\d+\s*章\s*.+|\d+\.\d+\s*.+)$'
)

# 短章节名称（如"存储系统"、"数据的表示和运算"等，出现在末尾时移除）
_SHORT_CHAPTER_RE = re.compile(
    r'^[\u4e00-\u9fff\w\s/·]+$'  # 纯中文/英文/数字/空格组成的短行
)


def _clean_footer(text: str) -> str:
    """移除题目文本尾部的 footer 残留。

    扫描末尾最多 10 行，移除所有匹配 footer 模式的行，
    包括夹在 footer 中间的章节标题行。
    """
    lines = text.split('\n')

    # 从末尾向前扫描，最多检查 10 行
    scan_limit = min(10, len(lines))
    remove_from = len(lines)  # 从此位置开始的行全部移除

    for i in range(len(lines) - 1, len(lines) - scan_limit - 1, -1):
        if i < 0:
            break
        stripped = lines[i].strip()

        # 空行：包含在移除范围内
        if not stripped:
            remove_from = i
            continue

        # 匹配 footer 模式
        is_footer = any(p.search(stripped) for p in _FOOTER_PATTERNS)
        if is_footer:
            remove_from = i
            continue

        # 匹配章节标题（如 "第3 章"、"3.2 主存储器"）
        if _CHAPTER_TITLE_RE.match(stripped):
            remove_from = i
            continue

        # 短章节名称（≤15字的纯中文标题，且前面已有 footer 被标记移除）
        if (remove_from < len(lines) and
                len(stripped) <= 15 and
                _SHORT_CHAPTER_RE.match(stripped)):
            remove_from = i
            continue

        # 非 footer 行，停止扫描
        break

    if remove_from < len(lines):
        lines = lines[:remove_from]

    # 移除尾部空行
    while lines and not lines[-1].strip():
        lines.pop()

    return '\n'.join(lines)


# ── 子问题间距 ──

_SUB_Q_RE = re.compile(r'\n([（(][1-9]\d*[）)])')


# ── 主清洗函数 ──


def clean_question_text(text: str) -> str:
    """清洗题目文本，返回可直接由 st.markdown() 渲染的格式。

    处理流程:
    0.  还原 <br> 为 \\n
    0.5 修复 PUA 字符
    1.  清理 PDF 装饰符号
    1.5 清理 footer
    2.  检测 C/C++ 代码块
    2.5 检测汇编代码块
    3.  子问题间距
    4.  分区换行处理
    5.  行内汇编标记
    """
    if not text:
        return text

    # ── Step 0: 还原已有的 <br> 标签为 \\n ──
    text = re.sub(r'<br\s*/?>', '\n', text)

    # ── Step 0.5: PUA 字符修复 ──
    text = _repair_pua(text)

    # ── Step 1: PDF 扫描清理 ──
    text = _clean_pdf_artifacts(text)

    # ── Step 1.5: Footer 清理 ──
    text = _clean_footer(text)

    # ── Step 2: 检测 C/C++ 代码块行范围 ──
    lines = text.split('\n')
    c_code_blocks = _detect_code_blocks(lines)

    # ── Step 2.5: 检测汇编代码块行范围 ──
    asm_blocks = _detect_assembly_blocks(lines)

    # 合并所有代码块（C + 汇编），处理重叠
    all_blocks = sorted(c_code_blocks + asm_blocks, key=lambda x: x[0])
    merged: list[tuple[int, int, str]] = []  # (start, end, lang)
    for start, end in all_blocks:
        # 判断是 C 代码还是汇编
        is_c = any(s <= start <= e for s, e in c_code_blocks)
        lang = 'c' if is_c else 'x86asm'
        # 合并重叠
        if merged and start <= merged[-1][1] + 1:
            prev_s, prev_e, prev_lang = merged[-1]
            merged[-1] = (prev_s, max(prev_e, end), prev_lang)
        else:
            merged.append((start, end, lang))

    # ── Step 3: 子问题间距 ──
    text = '\n'.join(lines)
    text = _SUB_Q_RE.sub(r'\n\n\n\1', text)
    lines = text.split('\n')

    # ── Step 4: 分区处理 — 代码块保留 \\n，其余 → 行尾双空格换行 ──
    code_line_map: dict[int, str] = {}  # line_idx -> language
    for start, end, lang in merged:
        for idx in range(start, min(end + 1, len(lines))):
            code_line_map[idx] = lang

    sections: list[str] = []
    current: list[str] = []
    in_code = False
    current_lang = ''

    for i, line in enumerate(lines):
        line_lang = code_line_map.get(i, '')
        is_code_line = bool(line_lang)

        if is_code_line and not in_code:
            # 进入代码块
            if current:
                sections.append('  \n'.join(current))
                current = []
            in_code = True
            current_lang = line_lang
            sections.append(f'```{current_lang}\n')

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
        sections.append('  \n'.join(current))

    result = ''.join(sections)

    # ── Step 5: 行内汇编关键词标记 ──
    result = _mark_inline_asm(result)

    return result


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
