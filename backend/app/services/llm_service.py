"""LLM Service — DeepSeek API integration via OpenAI-compatible client.

Provides:
- Chat completion for AI tutor conversations
- Vision/multimodal for PDF page image analysis (answer extraction)
- Streaming support for real-time chat UI
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Generator

from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger("llm_service")


# ─────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────

TUTOR_SYSTEM_PROMPT = """你是"408考研AI专属助教"，一个专门帮助计算机专业考研408科目复习的AI助手。

你的职责：
1. 讲解数据结构、操作系统、计算机组成原理、计算机网络四门课的核心知识点
2. 分析学生的错题，找出薄弱点并给出针对性讲解
3. 用通俗易懂的语言解释复杂概念，配合举例说明
4. 提供解题思路和方法论，不只是给答案
5. 鼓励学生思考，适时提出引导性问题

回答风格：
- 使用中文回答
- 条理清晰，重点突出
- 对考研常考知识点特别关注
- 涉及公式时用LaTeX格式
- 遇到不确定的内容要诚实说明

你可以通过工具查询题库中的题目信息来辅助回答。"""


VISION_SYSTEM_PROMPT = """你是一个PDF页面OCR助手。请仔细阅读提供的PDF页面图片，完成以下任务：

1. 识别页面中的所有题目及其选项
2. 如果页面包含答案（如"答案"、"解析"等部分），提取答案和解析内容
3. 用结构化JSON格式返回结果

返回格式：
```json
{
  "questions": [
    {
      "number": 题号,
      "text": "题目文本",
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "answer": "正确答案(如有)",
      "analysis": "解析(如有)"
    }
  ]
}
```

只返回JSON，不要有其他内容。"""


VLM_QUESTION_EXTRACT_PROMPT = """你是一个408考研题库OCR助手。请仔细阅读此PDF页面图片，提取所有题目信息。

识别要求：
1. 提取每道题的题号、题干文本、选项(A/B/C/D/E)
2. 如果页面顶部有章节标题（如"第X章"、"X.X 小节名"），记录到 context 中
3. 如果题目包含真题年份标记（如【2023统考真题】、【2021年真题】），提取到 exam_year 字段
4. 如果页面包含答案或解析部分，一并提取
5. 对于综合题/解答题（没有ABCD选项的），options 留空对象 {{}}
6. 数学公式使用LaTeX格式（$...$）

{context_hint}

严格返回以下JSON格式，不要有其他内容：
{{
  "context": {{
    "chapter": "第X章 章名(如有)",
    "section": "X.X 小节名(如有)"
  }},
  "questions": [
    {{
      "number": 题号,
      "text": "题干完整文本",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "答案字母(如有)",
      "analysis": "解析内容(如有)",
      "exam_year": "2023统考真题(如有，无则留空字符串)"
    }}
  ]
}}

如果该页面没有题目（如目录页、空白页），返回 {{"context": {{}}, "questions": []}}。
只返回JSON，不要有其他内容。"""


ANSWER_SYSTEM_PROMPT = """你是408计算机考研专业答题助手。给你一道408考研选择题，请给出正确答案和详细解析。

要求：
1. 答案必须是一个字母（A/B/C/D）
2. 解析要清晰，解释为什么选这个答案，以及为什么排除其他选项
3. 涉及关键知识点时要点明

严格返回JSON格式：
{"answer": "A", "analysis": "解析内容..."}

只返回JSON，不要有其他内容。"""


PUA_CORRECTION_PROMPT = """你是一个PDF页面数学符号修正助手。

下面的PDF页面图片中，文本提取工具无法正确识别某些数学符号（显示为乱码字符）。
请仔细观察图片，将以下题目文本中的乱码部分替换为正确的数学符号。

规则：
- 使用标准Unicode数学字符（如 ∈, ⊆, ×, ≤, ≥, ∞, ∑, ∫, √, ⊕, ₂ 等）
- 对于括号：使用标准 ( ) [ ] { }
- 对于无法用Unicode表示的复杂公式，使用LaTeX格式（$...$）
- 保持题目文本的其余部分不变，只修正乱码字符
- 选项文本同样需要修正（如有乱码）

需要修正的题目：
{questions_block}

严格返回JSON格式：
{{
  "corrections": [
    {{
      "question_id": 题目ID,
      "question_text": "修正后的题目正文",
      "option_a": "修正后的选项A(如有)",
      "option_b": "修正后的选项B(如有)",
      "option_c": "修正后的选项C(如有)",
      "option_d": "修正后的选项D(如有)"
    }}
  ]
}}

只返回JSON，不要有其他内容。"""


ESSAY_REFERENCE_PROMPT = """你是408计算机考研综合题/解答题的答题助手。给你一道综合题，请给出标准参考答案和详细解析。

要求：
1. 给出完整的、可直接作为标准答案的解答（含必要步骤、公式、结论）
2. 解析要条理清晰，点明考查的核心知识点
3. 不要尝试用 A/B/C/D 之类的字母作答——综合题没有选项

严格返回JSON格式：
{"answer": "参考答案正文...", "analysis": "解析内容..."}

只返回JSON，不要有其他内容。"""


# ─────────────────────────────────────────────
# LLM Client
# ─────────────────────────────────────────────

class LLMService:
    """DeepSeek LLM service using OpenAI-compatible API.

    Text completions go through the main LLM (DeepSeek).
    Vision/multimodal calls go through a separate vision client
    (通义千问VL by default, since DeepSeek doesn't support vision input).
    """

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm_model
        self.vision_model = settings.vision_model
        self._client: OpenAI | None = None
        self._vision_client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy-initialized OpenAI client pointing to DeepSeek."""
        if self._client is None:
            settings = get_settings()
            if not settings.llm_api_key or settings.llm_api_key == "sk-your-deepseek-api-key-here":
                raise RuntimeError(
                    "LLM API key not configured. "
                    "Set LLM_API_KEY in .env file."
                )
            self._client = OpenAI(
                base_url=settings.llm_api_base,
                api_key=settings.llm_api_key,
            )
        return self._client

    def is_configured(self) -> bool:
        """Check if LLM API is properly configured."""
        settings = get_settings()
        return bool(
            settings.llm_api_key
            and settings.llm_api_key != "sk-your-deepseek-api-key-here"
            and settings.llm_api_base
        )

    @property
    def vision_client(self) -> OpenAI:
        """Lazy-initialized OpenAI client for vision API (Qwen-VL / DashScope)."""
        if self._vision_client is None:
            settings = get_settings()
            if not settings.vision_api_key:
                raise RuntimeError(
                    "Vision API key not configured. "
                    "Set VISION_API_KEY in .env file to enable scanned PDF extraction."
                )
            self._vision_client = OpenAI(
                base_url=settings.vision_api_base,
                api_key=settings.vision_api_key,
            )
        return self._vision_client

    def is_vision_configured(self) -> bool:
        """Check if vision API is properly configured."""
        settings = get_settings()
        return bool(settings.vision_api_key and settings.vision_api_base)

    # ── Chat completion ──

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
        retry_error_cls=APIError,
    )
    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature (0-2).
            max_tokens: Maximum response tokens.

        Returns:
            The assistant's reply as a string.
        """
        full_messages = [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            *messages,
        ]

        logger.debug(f"LLM chat: {len(messages)} messages, model={self.model}")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        reply = response.choices[0].message.content or ""
        logger.info(
            f"LLM reply: {len(reply)} chars, "
            f"tokens={response.usage.total_tokens if response.usage else '?'}"
        )
        return reply

    def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Generator[str, None, None]:
        """Stream chat completion tokens.

        Yields:
            Individual text chunks from the response.
        """
        full_messages = [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            *messages,
        ]

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # ── Solve questions (AI answer generation) ──

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
    )
    def answer_question(
        self,
        question_text: str,
        options: dict[str, str] | None = None,
        subject: str = "",
    ) -> dict:
        """Use DeepSeek to solve a question and return answer + analysis.

        Args:
            question_text: The question text.
            options: Dict like {"A": "option text", "B": "...", ...}.
            subject: Subject name for context.

        Returns:
            Dict with 'answer' (str, e.g. "A") and 'analysis' (str).
            On failure returns {"answer": "", "analysis": ""}.
        """
        # Build user prompt
        prompt_parts = []
        if subject:
            prompt_parts.append(f"【{subject}】")
        prompt_parts.append(f"题目：{question_text}")

        if options:
            for letter in ["A", "B", "C", "D"]:
                if letter in options and options[letter]:
                    prompt_parts.append(f"{letter}. {options[letter]}")

        user_prompt = "\n".join(prompt_parts)

        # API errors propagate to trigger @retry; only non-API errors are caught
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
        )

        reply = (response.choices[0].message.content or "").strip()
        tokens = response.usage.total_tokens if response.usage else "?"
        logger.info(
            f"AI answered question: answer={reply[:20]}..., tokens={tokens}"
        )

        try:
            return self._parse_answer_json(reply)
        except Exception as e:
            logger.error(f"Failed to parse AI answer: {e}")
            return {"answer": "", "analysis": reply}

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
    )
    def answer_essay_question(
        self,
        question_text: str,
        subject: str = "",
    ) -> dict:
        """Generate a reference answer for a non-choice (综合/解答) question.

        Unlike answer_question, this does NOT return a letter grade — there is
        no objective single-letter answer. The returned text is a reference
        solution for the user to self-check against.

        Returns:
            Dict with 'answer' (reference solution) and 'analysis'.
            On failure returns {"answer": "", "analysis": ""}.
        """
        prompt_parts = []
        if subject:
            prompt_parts.append(f"【{subject}】")
        prompt_parts.append(f"题目：{question_text}")
        user_prompt = "\n".join(prompt_parts)

        # API errors propagate to trigger @retry
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": ESSAY_REFERENCE_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        reply = (response.choices[0].message.content or "").strip()
        tokens = response.usage.total_tokens if response.usage else "?"
        logger.info(
            f"AI reference answer for essay: tokens={tokens}, "
            f"reply_len={len(reply)}"
        )

        try:
            data = self._parse_answer_json_loose(reply)
            return {
                "answer": data.get("answer", ""),
                "analysis": data.get("analysis", ""),
            }
        except Exception as e:
            logger.error(f"Failed to parse essay reference: {e}")
            return {"answer": reply, "analysis": ""}

    @staticmethod
    def _parse_answer_json_loose(text: str) -> dict:
        """Parse JSON loosely; fall back to putting the whole text under 'answer'."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse essay reference JSON: {text[:200]}")
            return {"answer": text, "analysis": ""}

    @staticmethod
    def _parse_answer_json(text: str) -> dict:
        """Parse the AI's JSON answer response, with fallbacks."""
        # Remove markdown code fences
        text = text.strip()
        if text.startswith("```"):
            # Remove ```json ... ``` wrapper
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)

        try:
            data = json.loads(text)
            answer = str(data.get("answer", "")).strip().upper()
            analysis = str(data.get("analysis", "")).strip()
            # Validate answer is a single letter A-D
            if answer not in ("A", "B", "C", "D"):
                # Try to extract first A/B/C/D from text
                match = re.search(r"[ABCD]", answer)
                answer = match.group(0) if match else ""
            return {"answer": answer, "analysis": analysis}
        except (json.JSONDecodeError, KeyError):
            logger.warning(f"Failed to parse AI answer JSON: {text[:200]}")
            # Fallback: try to extract answer from text
            match = re.search(r'"answer"\s*:\s*"([ABCD])"', text, re.IGNORECASE)
            answer = match.group(1).upper() if match else ""
            return {"answer": answer, "analysis": text}

    # ── Vision / multimodal (for PDF answer extraction) ──

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=15),
    )
    def analyze_page_image(
        self,
        image_path: str,
        prompt: str | None = None,
    ) -> str:
        """Analyze a PDF page image using vision capabilities.

        Args:
            image_path: Path to the page image file.
            prompt: Optional custom prompt; defaults to OCR extraction.

        Returns:
            The model's text response (typically JSON).
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Encode image as base64
        image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        suffix = path.suffix.lower().lstrip(".")
        mime = f"image/{suffix}" if suffix != "jpg" else "image/jpeg"

        response = self.vision_client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_data}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt or "请提取此页面中的所有题目、答案和解析。",
                        },
                    ],
                },
            ],
            max_tokens=4000,
        )

        return response.choices[0].message.content or ""

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=15),
    )
    def analyze_questions_page(
        self,
        image_path: str,
        context: dict | None = None,
    ) -> dict:
        """Analyze a scanned PDF page image and extract structured question data.

        Uses the specialized VLM_QUESTION_EXTRACT_PROMPT for 408 question extraction.

        Args:
            image_path: Path to the rendered page image.
            context: Optional previous context dict with 'chapter' and 'section'
                     to help the model maintain continuity across pages.

        Returns:
            Parsed dict with 'context' and 'questions' keys.
            On failure returns {"context": {}, "questions": []}.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Build context hint for the model
        context_hint = ""
        if context:
            parts = []
            if context.get("chapter"):
                parts.append(f"当前章节: {context['chapter']}")
            if context.get("section"):
                parts.append(f"当前小节: {context['section']}")
            if parts:
                context_hint = "上下文提示（来自前序页面）:\n" + "\n".join(parts)

        prompt = VLM_QUESTION_EXTRACT_PROMPT.format(context_hint=context_hint)

        # Encode image as base64
        image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        suffix = path.suffix.lower().lstrip(".")
        mime = f"image/{suffix}" if suffix != "jpg" else "image/jpeg"

        response = self.vision_client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_data}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            max_tokens=4000,
            temperature=0.1,
        )

        reply = (response.choices[0].message.content or "").strip()
        logger.info(
            f"VLM page analysis: reply_len={len(reply)}"
        )

        return self._parse_answer_json_loose(reply)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
    )
    def correct_garbled_text(
        self,
        image_path: str,
        questions: list[dict],
    ) -> dict:
        """Send page image + garbled questions to vision LLM for PUA correction.

        Args:
            image_path: Path to rendered page PNG.
            questions: List of dicts with 'id', 'question_text', 'option_a'-'option_d'.

        Returns:
            Parsed JSON with 'corrections' list.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Build questions block for the prompt
        questions_block = []
        for q in questions:
            parts = [f"[ID={q['id']}] 题目: {q['question_text']}"]
            for letter in ("a", "b", "c", "d"):
                key = f"option_{letter}"
                if q.get(key):
                    parts.append(f"  {letter.upper()}. {q[key]}")
            questions_block.append("\n".join(parts))

        prompt = PUA_CORRECTION_PROMPT.format(
            questions_block="\n\n".join(questions_block)
        )

        # Encode image as base64
        image_data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        suffix = path.suffix.lower().lstrip(".")
        mime = f"image/{suffix}" if suffix != "jpg" else "image/jpeg"

        response = self.vision_client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_data}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            max_tokens=4000,
            temperature=0.1,
        )

        reply = (response.choices[0].message.content or "").strip()
        logger.info(
            f"PUA correction for page with {len(questions)} questions: "
            f"reply_len={len(reply)}"
        )

        return self._parse_answer_json_loose(reply)

    def pdf_page_to_image(self, pdf_path: str, page_num: int) -> str:
        """Convert a PDF page to a PNG image for vision analysis.

        Args:
            pdf_path: Path to the PDF file.
            page_num: 0-indexed page number.

        Returns:
            Path to the saved PNG image.
        """
        import fitz

        settings = get_settings()
        image_dir = Path(settings.image_dir)
        image_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_num]
            # Render at 2x resolution for better OCR
            pix = page.get_pixmap(dpi=200)
            stem = Path(pdf_path).stem
            img_path = image_dir / f"{stem}_page{page_num + 1}.png"
            pix.save(str(img_path))
            logger.info(f"Rendered page {page_num + 1} → {img_path}")
            return str(img_path)
        finally:
            doc.close()


# Singleton
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get the global LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
