"""真实 Provider：调用大模型 Chat Completions 兼容接口。

设计要点：
- 失败重试后抛 AIProviderError，**绝不自动降级到 Mock** —— 静默降级会把
  规则模板的输出伪装成 AI 评估结果，既误导用户又掩盖故障
- 大模型输出不完全可控，因此解析层做足容错（围栏剥离、子串提取、越界夹取）
"""

import json
import re
from typing import Any

import httpx

from app.ai.base import (
    DIFFICULTIES,
    DIFFICULTY_MEDIUM,
    SCORE_MAX,
    SCORE_MIN,
    SOURCE_AI,
    AIProvider,
    DimensionScoreResult,
    GeneratedQuestion,
    QAPair,
    QuestionScoreResult,
    ReportResult,
)
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_EMPTY_STRENGTHS = "本次面试暂无明显优势维度"
_EMPTY_WEAKNESSES = "本次面试暂无明显薄弱维度"


def _clamp_score(value: Any) -> float:
    """把任意返回值夹到 [0, 10] 并保留 1 位小数。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(max(number, SCORE_MIN), SCORE_MAX), 1)


class OpenAIProvider(AIProvider):
    """基于大模型 API 的实现。

    transport 参数用于测试注入 httpx.MockTransport，避免打真实 API。
    """

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        settings = get_settings()

        if not settings.openai_api_key:
            raise AIProviderError("使用真实 Provider 时必须配置 OPENAI_API_KEY")
        if not settings.openai_base_url:
            raise AIProviderError("使用真实 Provider 时必须配置 OPENAI_BASE_URL")
        if not settings.openai_model:
            raise AIProviderError("使用真实 Provider 时必须配置 OPENAI_MODEL")

        self._model = settings.openai_model
        self._endpoint = settings.openai_base_url.rstrip("/") + "/chat/completions"
        self._max_retries = settings.ai_max_retries
        self._client = httpx.Client(
            timeout=settings.ai_timeout_seconds,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    # ---------------------------- 传输层 ----------------------------

    def _request_json(
        self, system: str, user: str, temperature: float, expect_list: bool
    ) -> Any:
        """调用模型并解析 JSON。网络失败与解析失败共用同一重试计数。"""
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        last_error: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                response = self._client.post(self._endpoint, json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return self._parse_json(content, expect_list)
            except Exception as exc:  # noqa: BLE001 - 统一计入重试
                last_error = exc

        raise AIProviderError(
            f"AI 服务调用失败（已尝试 {self._max_retries + 1} 次）：{last_error}"
        ) from last_error

    @staticmethod
    def _parse_json(raw: str, expect_list: bool) -> Any:
        text = (raw or "").strip()

        # 1) 剥离 markdown 代码围栏
        fenced = _FENCE_RE.search(text)
        if fenced:
            text = fenced.group(1).strip()

        # 2) 提取首个 { 到最后一个 }（或 [ 到 ]），跳过前后解释性文字
        open_ch, close_ch = ("[", "]") if expect_list else ("{", "}")
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            text = text[start : end + 1]

        return json.loads(text)

    # ---------------------------- 出题 ----------------------------

    def generate_questions(
        self,
        position_name: str,
        jd: str,
        dims: list[str],
        existing_contents: list[str],
        count: int,
    ) -> list[GeneratedQuestion]:
        if not dims:
            raise AIProviderError("缺少评估维度，无法生成题目")
        if count <= 0:
            return []

        existing = "、".join(existing_contents) if existing_contents else "（无）"
        system = "你是一位资深面试官，负责根据岗位要求设计面试题。"
        user = (
            f"岗位名称：{position_name}\n"
            f"岗位描述（JD）：\n{jd}\n\n"
            f"评估维度（dimension 只能从中选择）：{json.dumps(dims, ensure_ascii=False)}\n"
            f"已有题目（新题不得与以下题目重复）：{existing}\n\n"
            f"请生成 {count} 道新题，输出 JSON 数组，每个元素包含：\n"
            '- "content"：题干\n'
            '- "dimension"：考察维度，必须是给定维度之一\n'
            '- "difficulty"：难度，取值 easy / medium / hard\n'
            '- "category"：分类\n'
            '- "tags"：标签数组\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.7, expect_list=True)
        if not isinstance(raw, list):
            raise AIProviderError("AI 返回的出题结果不是 JSON 数组")

        results: list[GeneratedQuestion] = []
        for item in raw[:count]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue

            dimension = self._coerce_dimension(item.get("dimension"), dims)
            if dimension is None:
                continue  # 无从判断归属维度，丢弃该条

            difficulty = item.get("difficulty")
            if difficulty not in DIFFICULTIES:
                difficulty = DIFFICULTY_MEDIUM

            tags = item.get("tags")
            if not isinstance(tags, list):
                tags = []

            results.append(
                GeneratedQuestion(
                    content=content,
                    dimension=dimension,
                    difficulty=difficulty,
                    category=str(item.get("category") or "通用"),
                    tags=[str(t) for t in tags],
                    source=SOURCE_AI,
                )
            )

        return results

    @staticmethod
    def _coerce_dimension(value: Any, dims: list[str]) -> str | None:
        """把模型返回的维度映射到给定维度；无法判断则返回 None。"""
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        for dim in dims:  # 精确匹配
            if text == dim:
                return dim
        for dim in dims:  # 包含关系兜底
            if text in dim or dim in text:
                return dim
        return None

    # -------------------------- 逐题评分 --------------------------

    def evaluate_answer(
        self, dimension: str, question: str, answer: str | None
    ) -> QuestionScoreResult:
        system = "你是一位严谨的面试评估专家。"
        user = (
            f"考察维度：{dimension}\n"
            f"面试题目：{question}\n"
            f"候选人回答：{answer.strip() if answer and answer.strip() else '（未作答）'}\n\n"
            "请对该回答打分，分值区间 0–10（可含 1 位小数）。"
            "评分应综合考虑具体性、相关性与深度；未作答记 0 分。\n"
            '输出 JSON 对象：{"score": 数值, "comment": "评语"}\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的单题评分不是 JSON 对象")

        comment = str(raw.get("comment") or "").strip()
        return QuestionScoreResult(
            score=_clamp_score(raw.get("score")), comment=comment or "无评语"
        )

    # -------------------------- 多维评分 --------------------------

    def evaluate_dimensions(
        self, dims: list[str], qa_pairs: list[QAPair]
    ) -> list[DimensionScoreResult]:
        if not dims:
            return []

        pairs_text = "\n".join(
            f"- 维度：{p.dimension}｜题目：{p.question}｜回答："
            f"{(p.answer.strip() if p.answer and p.answer.strip() else '（未作答）')}"
            for p in qa_pairs
        )
        system = "你是一位严谨的面试评估专家。"
        user = (
            f"需要评估的维度（每个维度都必须给出评分）：{json.dumps(dims, ensure_ascii=False)}\n\n"
            f"本次面试的问答记录：\n{pairs_text or '（无）'}\n\n"
            "请对每个维度综合打分，分值区间 0–10（可含 1 位小数）。"
            "某维度若没有对应题目，记 0 分。\n"
            "输出 JSON 数组，每个元素："
            '{"dimension": "维度名", "score": 数值, "comment": "评语"}\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=True)
        if not isinstance(raw, list):
            raise AIProviderError("AI 返回的多维评分不是 JSON 数组")

        by_dimension: dict[str, DimensionScoreResult] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            dimension = self._coerce_dimension(item.get("dimension"), dims)
            if dimension is None or dimension in by_dimension:
                continue
            by_dimension[dimension] = DimensionScoreResult(
                dimension=dimension,
                score=_clamp_score(item.get("score")),
                comment=str(item.get("comment") or "").strip() or "无评语",
            )

        # 保证覆盖全部维度、且顺序与传入 dims 一致；缺失的按 0 分处理
        return [
            by_dimension.get(
                dim,
                DimensionScoreResult(
                    dimension=dim,
                    score=0.0,
                    comment="该维度在本次面试中无对应题目。",
                ),
            )
            for dim in dims
        ]

    # -------------------------- 汇总报告 --------------------------

    def summarize_report(
        self,
        dims: list[str],
        dimension_scores: list[DimensionScoreResult],
        question_scores: list[QuestionScoreResult],
    ) -> ReportResult:
        dimension_text = "\n".join(
            f"- {d.dimension}：{d.score:.1f}（{d.comment}）" for d in dimension_scores
        )
        question_text = "\n".join(
            f"- {q.score:.1f}（{q.comment}）" for q in question_scores
        )
        system = "你是一位资深的招聘评估专家。"
        user = (
            f"维度得分：\n{dimension_text or '（无）'}\n\n"
            f"逐题得分：\n{question_text or '（无）'}\n\n"
            "请汇总生成面试报告，总分区间 0–10（可含 1 位小数）。\n"
            "输出 JSON 对象，字段：\n"
            '- "overall_score"：总分（数值）\n'
            '- "conclusion"：综合结论（字符串）\n'
            '- "strengths"：优势（**字符串数组**）\n'
            '- "weaknesses"：待改进（**字符串数组**）\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的汇总报告不是 JSON 对象")

        strengths = self._str_list(raw.get("strengths")) or [_EMPTY_STRENGTHS]
        weaknesses = self._str_list(raw.get("weaknesses")) or [_EMPTY_WEAKNESSES]

        return ReportResult(
            overall_score=_clamp_score(raw.get("overall_score")),
            conclusion=str(raw.get("conclusion") or "").strip() or "无结论",
            strengths=strengths,
            weaknesses=weaknesses,
        )

    @staticmethod
    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
