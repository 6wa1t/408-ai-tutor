import sys
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parents[1].parent / "frontend"
sys.path.insert(0, str(FRONTEND_ROOT))

from shared.question_rendering import (  # noqa: E402
    sanitize_table_html,
    split_question_text,
    strip_markdown_images,
)


def test_strip_markdown_images_removes_inline_image_references():
    text = "Before\n\n![](images/diagram.jpg)\n\nAfter"

    assert strip_markdown_images(text) == "Before\n\nAfter"


def test_split_question_text_preserves_table_as_html_part():
    text = (
        "Before table\n"
        "<table><tr><td rowspan=1 colspan=1>A</td></tr></table>\n"
        "After table"
    )

    parts = split_question_text(text)

    assert [part.kind for part in parts] == ["markdown", "table_html", "markdown"]
    assert parts[0].content == "Before table"
    assert parts[1].content.startswith("<table>")
    assert parts[2].content == "After table"


def test_sanitize_table_html_removes_unsafe_html_and_event_attrs():
    html = (
        '<table onclick="alert(1)"><tr><td>ok</td></tr></table>'
        '<script>alert(1)</script>'
    )

    cleaned = sanitize_table_html(html)

    assert "onclick" not in cleaned
    assert "<script>" not in cleaned
    assert "<table>" in cleaned


def test_split_question_text_normalizes_corrupt_c_code_fences():
    text = (
        "Before\n\n"
        "```lisp```c\n"
        "int f1(unsigned n) {\n"
        "return n;\n"
        "}\n"
        "```\n"
        "```\n\n"
        "After"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    assert "```c\nint f1" in parts[0].content
    assert "```\n\nAfter" in parts[0].content
    assert "```lisp```c" not in parts[0].content
    assert "```\n```\n\nAfter" not in parts[0].content


def test_split_question_text_merges_orphan_c_statement_after_fence():
    text = (
        "```javascript```c\n"
        "int x,d[2048],i;\n"
        "for(i=0;i<2048;i++)\n"
        "```\n"
        "d[i]=d[i]/x;\n"
        "```\n\n"
        "(1) question"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert "```c\nint x" in content
    assert "for(i=0;i<2048;i++)\nd[i]=d[i]/x;\n```" in content
    assert "```\nd[i]" not in content
    assert "```\n\n(1) question" in content


def test_split_question_text_unwraps_question_sentence_from_code_fence():
    text = (
        "(1) first\n"
        "```x86asm\n\n"
        "(2) 假定inc、shl和sub指令的操作码分别为01H、02H和03H，"
        "则以下指令对应的机器代码各是什么？\n"
        "```\n\n"
        "`inc` R1; (R1) + 1 -> R1\n"
        "`shl` R2, R1 ; (R1) << 1 -> R2\n"
        "`sub` R3, (R1), R2 ; ((R1)) - (R2) -> R3"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert "```x86asm" not in content
    assert "(2) 假定inc" in content
    assert "```asm\ninc R1;" in content
    assert "`inc` R1" not in content


def test_split_question_text_converts_latex_array_math_to_table_part():
    text = (
        "Before\n\n"
        "$$\n"
        "{ \\begin{array} { r l } { 1 } & { \\mathrm { mov } R1 } \\\\ "
        "{ 2 } & { \\operatorname { add } R2 } \\end{array} }\n"
        "$$\n\n"
        "After"
    )

    parts = split_question_text(text)

    assert [part.kind for part in parts] == ["markdown", "table_html", "markdown"]
    assert "<table" in parts[1].content
    assert "begin{array}" not in parts[1].content
    assert "mov R1" in parts[1].content


def test_split_question_text_merges_for_loop_continuation_after_code_fence():
    text = (
        "Before\n"
        "```c\n"
        "int a[128][128];\n"
        "for(int i=0;i<128;i++)\n"
        "```\n"
        "for(int j=0;j<128;j++)\n"
        "a[j][i]=0;\n"
        "```\n"
        "After"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert content.count("```") == 2
    assert "for(int i=0;i<128;i++)\nfor(int j=0;j<128;j++)\na[j][i]=0;" in content
    assert "```\nfor(int j" not in content
    assert "```\nAfter" in content


def test_split_question_text_removes_nested_inline_code_fence_marker():
    text = (
        "```c\n"
        "char *ptr;\n"
        "void main()\n"
        "{```c\n"
        "int length;\n"
        "ptr = (char *)malloc(100);\n"
        "```\n"
        "scanf(\"%s\", ptr);\n"
        "length = strlen(ptr);\n"
        "```\n"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert content.count("```") == 2
    assert "{```c" not in content
    assert "void main()\n{\nint length;" in content
    assert "scanf" in content


def test_split_question_text_preserves_inline_fence_that_starts_code_block():
    text = (
        "instruction table```x86asm\n"
        "add 0000000 rs2 rs1 000 rd 0110011\n"
        "lw imm rs1 010 rd 0000011\n"
        "```\n"
        "After"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert content.count("```") == 2
    assert "instruction table\n```x86asm" in content
    assert "```\nAfter" in content


def test_split_question_text_keeps_prose_after_duplicate_empty_fence_outside_code():
    text = (
        "```c\n"
        "typedef struct {\n"
        "    int value;\n"
        "} Node;\n"
        "```\n"
        "```\n"
        "Chinese prose with T1.ElemNum=10 should not be code.\n"
        "```mermaid\n"
        "graph TD\n"
        "```"
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert content.count("```") == 4
    assert "```\nChinese prose" in content
    assert "Chinese prose" not in content.split("```c", 1)[1].split("```", 1)[0]


def test_split_question_text_removes_mineru_details_blocks():
    text = (
        "Before diagram.\n\n"
        "<details>\n"
        "<summary>flowchart</summary>\n\n"
        "```mermaid\n"
        "graph TD\n"
        "A --> B\n"
        "```\n"
        "</details>\n\n"
        "After diagram."
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert "Before diagram." in content
    assert "After diagram." in content
    assert "<details" not in content
    assert "</details>" not in content
    assert "flowchart" not in content
    assert "mermaid" not in content


def test_split_question_text_removes_single_line_mineru_details_block():
    text = (
        "Question text\n"
        "<details> <summary>text_image</summary>\n"
        "S1\n192.168.3.1\n00-1a-2b-3c-4d-51\n"
        "</details>\n"
        "Choose one."
    )

    parts = split_question_text(text)

    assert len(parts) == 1
    content = parts[0].content
    assert "Question text" in content
    assert "Choose one." in content
    assert "text_image" not in content
    assert "192.168.3.1" not in content
    assert "<summary>" not in content


def test_split_question_text_converts_latex_inside_html_table_cells():
    text = (
        "Before\n"
        "<table><tr>"
        "<td>指令功能</td>"
        "<td>$\\left( \\mathrm{{Rs}}\\right) + \\left( \\mathrm{{Rd}}\\right) \\rightarrow \\mathrm{{Rd}}$</td>"
        "</tr></table>\n"
        "After"
    )

    parts = split_question_text(text)

    assert [part.kind for part in parts] == ["markdown", "table_html", "markdown"]
    table = parts[1].content
    assert "\\left" not in table
    assert "\\mathrm" not in table
    assert "\\rightarrow" not in table
    assert "$" not in table
    assert "(Rs) + (Rd) -> Rd" in table
