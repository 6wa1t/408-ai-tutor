"""Tests for the PDF parser module — tailored for 王道408题本 format.

Uses constructed text samples (not real PDFs) to test regex patterns
and parsing logic.
"""

import pytest

from app.services.pdf_parser import (
    PyMuPDFStrategy,
    PDFParser,
    ParsedQuestion,
    infer_subject,
    clean_page_text,
    CHAPTER_HEADING,
    SECTION_HEADING,
    QUESTION_NUM,
    OPTION_LINE,
    ANSWER_REF_PATTERN,
    EXAM_YEAR_PATTERN,
    QUESTION_SECTION_HEADER,
)


class TestInferSubject:
    """Test subject inference from file paths (checks parent dirs)."""

    def test_data_structure_from_parent_dir(self):
        assert infer_subject("/pdfs/数据结构/题本.pdf") == "数据结构"

    def test_data_structure_from_filename(self):
        assert infer_subject("/some/path/数据结构真题2023.pdf") == "数据结构"

    def test_operating_system(self):
        assert infer_subject("/pdfs/操作系统/题本.pdf") == "操作系统"

    def test_computer_organization(self):
        assert infer_subject("/path/计算机组成原理/王道题本.pdf") == "计算机组成原理"
        assert infer_subject("/path/组成原理真题.pdf") == "计算机组成原理"

    def test_computer_network(self):
        assert infer_subject("/pdfs/计算机网络/题本.pdf") == "计算机网络"

    def test_unknown(self):
        assert infer_subject("/some/path/408真题合集.pdf") == "未知科目"


class TestCleanPageText:
    """Test footer noise removal."""

    def test_remove_gongzhonghao(self):
        text = "题目内容\n公众号：做题本集结地\n下一题"
        result = clean_page_text(text)
        assert "公众号" not in result
        assert "题目内容" in result

    def test_remove_wd_footer(self):
        text = "题目内容\nWD·数据结构· 1.绪论\n· 第3 页，共10 页·"
        result = clean_page_text(text)
        assert "WD·" not in result
        assert "第3 页" not in result

    def test_remove_wangdao_footer(self):
        text = "题目\n王道计组课后选择题·1.概述\n· 第5 页，共20 页·"
        result = clean_page_text(text)
        assert "王道" not in result

    def test_normalize_blank_lines(self):
        text = "第一行\n\n\n\n\n第二行"
        result = clean_page_text(text)
        assert "\n\n\n" not in result

    def test_preserve_content(self):
        text = "下列关于二叉树的说法\nA. 选项A\nB. 选项B"
        result = clean_page_text(text)
        assert "二叉树" in result
        assert "选项A" in result


class TestRegexPatterns:
    """Test individual regex patterns with sample text."""

    def test_chapter_heading(self):
        text = "\n第 1 章 绪论"
        m = CHAPTER_HEADING.search(text)
        assert m is not None
        assert m.group(1) == "1"
        assert "绪论" in m.group(2)

    def test_chapter_heading_no_space(self):
        text = "\n第3章 栈和队列"
        m = CHAPTER_HEADING.search(text)
        assert m is not None
        assert m.group(1) == "3"

    def test_section_heading(self):
        text = "\n1.1 数据结构的基本概念"
        m = SECTION_HEADING.search(text)
        assert m is not None
        assert m.group(1) == "1.1"
        assert "基本概念" in m.group(2)

    def test_section_heading_two_digit(self):
        text = "\n12.3 磁盘存储器"
        m = SECTION_HEADING.search(text)
        assert m is not None
        assert m.group(1) == "12.3"

    def test_question_num_dot(self):
        text = "\n1. 下列关于树的叙述中"
        m = QUESTION_NUM.search(text)
        assert m is not None
        assert m.group(1) == "1"

    def test_question_num_chinese_dot(self):
        text = "\n12、以下关于图的描述"
        m = QUESTION_NUM.search(text)
        assert m is not None
        assert m.group(1) == "12"

    def test_question_num_fullwidth_dot(self):
        text = "\n3．关于进程的说法"
        m = QUESTION_NUM.search(text)
        assert m is not None
        assert m.group(1) == "3"

    def test_option_line(self):
        text = "\nA. 二叉树是度为2的树"
        m = OPTION_LINE.search(text)
        assert m is not None
        assert m.group(1) == "A"

    def test_option_line_chinese(self):
        text = "\nB、左右子树可以交换"
        m = OPTION_LINE.search(text)
        assert m is not None
        assert m.group(1) == "B"

    def test_option_line_e(self):
        """Some questions have 5 options (A-E)."""
        text = "\nE. 以上都不对"
        m = OPTION_LINE.search(text)
        assert m is not None
        assert m.group(1).upper() == "E"

    def test_answer_ref(self):
        text = "（答案见原书P6）"
        m = ANSWER_REF_PATTERN.search(text)
        assert m is not None
        assert m.group(1) == "6"

    def test_answer_ref_variant(self):
        text = "答案见P4"
        m = ANSWER_REF_PATTERN.search(text)
        assert m is not None
        assert m.group(1) == "4"

    def test_answer_ref_section(self):
        text = "该节答案见原书P12"
        m = ANSWER_REF_PATTERN.search(text)
        assert m is not None
        assert m.group(1) == "12"

    def test_exam_year(self):
        text = "【2023 统考真题】"
        m = EXAM_YEAR_PATTERN.search(text)
        assert m is not None
        assert m.group(1) == "2023"

    def test_exam_year_no_tongkao(self):
        text = "【2021真题】"
        m = EXAM_YEAR_PATTERN.search(text)
        assert m is not None
        assert m.group(1) == "2021"

    def test_question_section_header(self):
        text = "一、单项选择题（答案见P4）"
        m = QUESTION_SECTION_HEADER.search(text)
        assert m is not None

    def test_question_section_header_variant(self):
        text = "二、综合题"
        m = QUESTION_SECTION_HEADER.search(text)
        assert m is not None


class TestParseQuestionBlock:
    """Test parsing individual question blocks."""

    def setup_method(self):
        self.strategy = PyMuPDFStrategy()

    def test_basic_choice_question(self):
        block = """1. 下列关于二叉树的说法中，正确的是
A. 二叉树是度为2的树
B. 二叉树的左右子树可以交换
C. 完全二叉树一定是满二叉树
D. 二叉树有且仅有一个根节点"""

        q = self.strategy._parse_question_block(
            block, q_num=1, section="1.1 基本概念", answer_ref="", exam_year=""
        )
        assert q is not None
        assert "二叉树" in q.question_text
        assert len(q.options) == 4
        assert "A" in q.options
        assert "度为2" in q.options["A"]
        assert q.question_number == 1
        assert q.section == "1.1 基本概念"

    def test_question_with_exam_year(self):
        block = """5. 【2023 统考真题】某计算机的Cache采用4路组相联映射
A. 选项A
B. 选项B
C. 选项C
D. 选项D"""

        q = self.strategy._parse_question_block(
            block, q_num=5, section="3.1 Cache", answer_ref="", exam_year="2023统考真题"
        )
        assert q is not None
        assert "【" not in q.question_text  # exam year marker removed
        assert "Cache" in q.question_text
        assert q.exam_year == "2023统考真题"
        assert "2023统考真题" in q.knowledge_tag

    def test_question_no_options(self):
        block = "12. 请简述进程和线程的主要区别。"

        q = self.strategy._parse_question_block(
            block, q_num=12, section="2.1 进程", answer_ref="", exam_year=""
        )
        assert q is not None
        assert "进程和线程" in q.question_text
        assert len(q.options) == 0

    def test_knowledge_tags_built(self):
        block = """3. 关于栈的描述
A. 先进后出
B. 先进先出
C. 随机访问
D. 顺序存储"""

        q = self.strategy._parse_question_block(
            block, q_num=3, section="2.3 栈和队列", answer_ref="", exam_year="2022统考真题"
        )
        assert "2.3 栈和队列" in q.knowledge_tag
        assert "2022统考真题" in q.knowledge_tag

    def test_five_options(self):
        """Some questions have option E."""
        block = """7. 下列关于中断的说法
A. 中断是硬件触发的
B. 异常是软件触发的
C. 中断和异常都需要陷入内核
D. 外部中断属于异常
E. 以上都不对"""

        q = self.strategy._parse_question_block(
            block, q_num=7, section="", answer_ref="", exam_year=""
        )
        assert len(q.options) == 5
        assert "E" in q.options

    def test_trailing_footer_cleaned(self):
        """Options should not contain footer noise."""
        block = """2. 下列说法正确的是
A. 选项A的内容
B. 选项B的内容
C. 选项C的内容公众号：做题本集结地
D. 选项D的内容"""

        q = self.strategy._parse_question_block(
            block, q_num=2, section="", answer_ref="", exam_year=""
        )
        # The last option may contain footer — the parser cleans it
        for letter, text in q.options.items():
            assert "公众号" not in text


class TestParseFullText:
    """Test full text parsing with section context tracking."""

    def setup_method(self):
        self.strategy = PyMuPDFStrategy()

    def test_section_context_tracking(self):
        text = """第 1 章 绪论

1.1 数据结构的基本概念

1. 下列关于数据结构的说法
A. 选项A
B. 选项B
C. 选项C
D. 选项D

2. 第二题内容
A. 选项A
B. 选项B
C. 选项C
D. 选项D"""

        questions = self.strategy._parse_full_text(text, "数据结构")
        assert len(questions) == 2
        # Both questions should have section context
        assert questions[0].section == "1.1 数据结构的基本概念"

    def test_multiple_sections(self):
        text = """第 2 章 线性表

2.1 线性表的定义

1. 关于线性表的说法
A. 选项A
B. 选项B
C. 选项C
D. 选项D

2.2 顺序表

3. 关于顺序表
A. 选项A
B. 选项B
C. 选项C
D. 选项D"""

        questions = self.strategy._parse_full_text(text, "数据结构")
        assert len(questions) == 2
        assert questions[0].section == "2.1 线性表的定义"
        assert questions[1].section == "2.2 顺序表"

    def test_answer_ref_propagation(self):
        """Answer ref from section header should apply to all questions in that section."""
        text = """1.1 基本概念
一、单项选择题（答案见原书P4）

1. 第一题
A. A
B. B
C. C
D. D

2. 第二题
A. A
B. B
C. C
D. D"""

        questions = self.strategy._parse_full_text(text, "数据结构")
        assert len(questions) == 2
        # Both should inherit the answer ref
        for q in questions:
            assert "P4" in q.answer_ref or q.answer_ref != ""

    def test_exam_year_extraction(self):
        text = """1.1 概述

1. 【2023 统考真题】这道题考查
A. 选项A
B. 选项B
C. 选项C
D. 选项D

2. 普通题目不含年份标记
A. 选项A
B. 选项B
C. 选项C
D. 选项D"""

        questions = self.strategy._parse_full_text(text, "数据结构")
        assert len(questions) == 2
        assert questions[0].exam_year == "2023统考真题"
        assert questions[1].exam_year == ""


class TestPDFParserFacade:
    """Test the PDFParser facade."""

    def test_default_strategy(self):
        parser = PDFParser()
        assert isinstance(parser.strategy, PyMuPDFStrategy)

    def test_custom_strategy(self):
        class MockStrategy:
            def parse(self, pdf_path):
                return [ParsedQuestion(question_text="mock")]

        parser = PDFParser(strategy=MockStrategy())
        results = parser.parse("fake.pdf")
        assert len(results) == 1
        assert results[0].question_text == "mock"

    def test_parse_with_text_hash(self):
        class MockStrategy:
            def parse(self, pdf_path):
                return [
                    ParsedQuestion(question_text="第一题"),
                    ParsedQuestion(question_text="第二题"),
                ]

        parser = PDFParser(strategy=MockStrategy())
        results = parser.parse_with_text_hash("fake.pdf")
        assert len(results) == 2
        # Each result is (ParsedQuestion, hash_string)
        for q, h in results:
            assert isinstance(h, str)
            assert len(h) == 64  # SHA256 hex digest length
        # Different texts → different hashes
        assert results[0][1] != results[1][1]


class TestParsedQuestion:
    """Test the ParsedQuestion dataclass."""

    def test_default_values(self):
        q = ParsedQuestion()
        assert q.question_text == ""
        assert q.options == {}
        assert q.answer == ""
        assert q.analysis == ""
        assert q.knowledge_tag == []
        assert q.image_paths == []
        assert q.question_number is None
        assert q.section == ""
        assert q.answer_ref == ""
        assert q.exam_year == ""

    def test_with_all_fields(self):
        q = ParsedQuestion(
            question_text="测试题目",
            options={"A": "选项A", "B": "选项B"},
            answer="A",
            analysis="解析内容",
            knowledge_tag=["1.1 概述"],
            question_number=5,
            section="1.1 概述",
            answer_ref="答案见原书P6",
            exam_year="2023统考真题",
        )
        assert q.question_number == 5
        assert q.section == "1.1 概述"
        assert q.answer_ref == "答案见原书P6"
        assert q.exam_year == "2023统考真题"
