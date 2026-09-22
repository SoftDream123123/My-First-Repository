"""真实 Provider：调用大模型 Chat Completions 兼容接口。

设计要点：
- 失败重试后抛 AIProviderError，**绝不自动降级到 Mock** —— 静默降级会把
  规则模板的输出伪装成 AI 评估结果，既误导用户又掩盖故障
- 大模型输出不完全可控，因此解析层做足容错（围栏剥离、子串提取、越界夹取）
"""

import json
import logging
import re
from typing import Any

import httpx

from app.ai.base import (
    CANDIDATE_FEEDBACK_LEAD,
    DIFFICULTIES,
    DIFFICULTY_MEDIUM,
    FEEDBACK_LEVEL_FULL,
    FEEDBACK_LEVEL_SUMMARY,
    FEEDBACK_LEVELS,
    PASS_THRESHOLD,
    QUESTION_TYPE_SINGLE_CHOICE,
    RESUME_REVIEW_MAX_ITEMS,
    SCORE_MAX,
    SCORE_MIN,
    SOURCE_AI,
    AIProvider,
    CandidateFeedbackResult,
    DimensionScoreResult,
    GeneratedQuestion,
    InterviewPrepResult,
    MatchedQuestion,
    PracticeGradeResult,
    PrepFocusPoint,
    PrepOutlineStage,
    PrepQuestionItem,
    QAPair,
    QuestionBrief,
    QuestionScoreResult,
    ReferenceAnswerResult,
    ReportResult,
    ResumeReviewResult,
)
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_EMPTY_STRENGTHS = "本次面试暂无明显优势维度"
_EMPTY_WEAKNESSES = "本次面试暂无明显薄弱维度"

# 匹配理由缺失时的兜底文案（不因理由为空而丢掉一道合法题目）
_MATCH_FALLBACK_REASON = "与岗位评估维度相关。"

# 准备提纲里 duration_min 非法时的回落值
_PREP_DEFAULT_DURATION_MIN = 5

# 无简历时写进 prompt 的**显式声明**。不省略该段：省略会让模型自行假设候选人
# 有简历，产出「针对简历中提到的…」这类引用不存在内容的提纲。
_NO_RESUME_TEXT = "（候选人未提供简历）"
_NO_QUESTIONS_TEXT = "（无）"

# 简历评估：岗位名缺失时的兜底，以及模型没给结论时的兜底句。
# 兜底句只陈述「没产出结论这件事」，**不得**退回任何含去留判断的说法（PRD §4.9）。
_REVIEW_DEFAULT_POSITION = "该岗位"
_REVIEW_NO_CONCLUSION = "已按岗位评估维度完成匹配度评估，详见亮点与差距两条列表。"


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
            "注意：strengths / weaknesses 的每条只描述维度上的表现，"
            "**不得出现任何数字或分数**（这些条目会原样下发给候选人，"
            "而候选人不该看到维度分）。\n"
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

    # ------------------------ 补参考答案 ------------------------

    def generate_reference_answer(
        self,
        question_type: str,
        content: str,
        options: list[str],
        dimension: str,
    ) -> ReferenceAnswerResult:
        if question_type == QUESTION_TYPE_SINGLE_CHOICE:
            if not options:
                raise AIProviderError("缺少选项，无法生成参考答案")
            options_text = "\n".join(
                f"{i + 1}. {opt}" for i, opt in enumerate(options)
            )
            answer_rule = (
                '本题是单选题，"reference_answer" 必须是上面选项中的**原文之一**，'
                "不得改写、不得给出选项之外的内容。\n"
            )
        else:
            options_text = "（本题为简答题，无选项）"
            answer_rule = '本题是简答题，"reference_answer" 为完整的参考答案文本。\n'

        system = "你是一位资深面试官与命题人，负责为面试题撰写标准答案与解析。"
        user = (
            f"考察维度：{dimension}\n"
            f"题型：{question_type}\n"
            f"题干：{content}\n"
            f"选项：\n{options_text}\n\n"
            f"请给出该题的标准答案与解析。{answer_rule}"
            "输出 JSON 对象，字段：\n"
            '- "reference_answer"：参考答案\n'
            '- "explanation"：解析（说明为什么是这个答案）\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的参考答案不是 JSON 对象")

        answer = str(raw.get("reference_answer") or "").strip()
        if not answer:
            # 不猜、不填默认值
            raise AIProviderError("AI 返回内容缺少 reference_answer 字段")

        # 注意：单选题的答案若不在 options 内，**不在此处纠正**。
        # 静默吸附到某个选项等于伪造正确答案；那是题目数据自洽性问题，
        # 由 question.service 判定并报 409（module-10 §5.2）。
        return ReferenceAnswerResult(
            reference_answer=answer,
            explanation=str(raw.get("explanation") or "").strip() or "无解析",
        )

    # -------------------------- 刷题判分 --------------------------

    def grade_practice_answer(
        self,
        question_type: str,
        content: str,
        reference_answer: str,
        user_answer: str,
    ) -> PracticeGradeResult:
        text = (user_answer or "").strip()

        # 空作答短路：不发网络请求
        if not text:
            return PracticeGradeResult(
                score=SCORE_MIN, is_correct=False, explanation="未作答"
            )

        reference = (reference_answer or "").strip()
        if not reference:
            # 不为空答案去调模型 —— 那只会得到臆造的判分
            raise AIProviderError("该题缺少参考答案，无法判分")

        system = "你是一位严格但公允的判卷人，负责按参考答案评判考生作答。"
        user = (
            f"题型：{question_type}\n"
            f"题干：{content}\n"
            f"参考答案：{reference}\n"
            f"候选人作答：{text}\n\n"
            "请对候选人的作答打分，分值区间 0–10（可含 1 位小数），"
            "衡量其与参考答案的要点吻合程度。\n"
            "输出 JSON 对象，字段：\n"
            '- "score"：分数（数值）\n'
            '- "explanation"：面向候选人的解析，指出漏掉或答错的要点\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的判分结果不是 JSON 对象")
        if "score" not in raw:
            raise AIProviderError("AI 返回内容缺少 score 字段")

        score = _clamp_score(raw.get("score"))

        # is_correct 一律由本地按唯一阈值推导，忽略模型可能返回的同名字段 ——
        # 否则「是否判对」会出现第二个判据（module-11 §5.2）
        return PracticeGradeResult(
            score=score,
            is_correct=score >= PASS_THRESHOLD,
            explanation=str(raw.get("explanation") or "").strip() or "无解析",
        )

    # ------------------------ 候选人反馈 ------------------------

    def generate_candidate_feedback(
        self,
        level: str,
        overall_score: float,
        strengths: list[str],
        weaknesses: list[str],
        dimension_scores: list[DimensionScoreResult],
    ) -> CandidateFeedbackResult:
        if level not in FEEDBACK_LEVELS:
            logger.warning("未知的候选人反馈档位 %r，已按 summary 处理", level)
            level = FEEDBACK_LEVEL_SUMMARY

        score_text = (
            f"总分：{overall_score:.1f}（可以告知候选人）\n"
            if level == FEEDBACK_LEVEL_FULL
            else "总分：**不得**向候选人提及\n"
        )
        dim_text = json.dumps(
            [{"维度": item.dimension, "得分": item.score} for item in dimension_scores],
            ensure_ascii=False,
        )

        # 报告那句综合结论**不进 prompt**（PRD §4.9）：它含招聘方的去留判断。
        # 不传是结构上的保证 —— 只叮嘱「不要复述」，等于把不该给的东西给了再要求别看。
        system = (
            "你是一位面向候选人的沟通者，负责把面试的评分事实转写成建设性的反馈。"
            "措辞要具体、尊重、可改进。你**拿不到**招聘方的录用结论，也不要据此"
            "推断录用与否；只讲候选人这一场的表现：强在哪、弱在哪。"
        )
        user = (
            f"各维度得分（满分 10）：{dim_text}\n"
            f"优点：{json.dumps(strengths, ensure_ascii=False)}\n"
            f"待改进：{json.dumps(weaknesses, ensure_ascii=False)}\n"
            f"{score_text}\n"
            "请写一段面向候选人本人的综合结论（2–3 句，只讲本场表现，"
            "不要复述下面两条列表里的原话），并保持优缺点的**条目数量与顺序**不变。\n"
            "输出 JSON 对象，字段：\n"
            '- "conclusion"：综合结论\n'
            '- "strengths"：优点（字符串数组）\n'
            '- "weaknesses"：待改进（字符串数组）\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.4, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的候选人反馈不是 JSON 对象")

        return CandidateFeedbackResult(
            # 模型没给结论时兜一句没有信息量的话 —— **不能**退回报告那句结论，
            # 那里面有去留判断（PRD §4.9）
            conclusion=str(raw.get("conclusion") or "").strip()
            or CANDIDATE_FEEDBACK_LEAD,
            strengths=self._str_list(raw.get("strengths")),
            weaknesses=self._str_list(raw.get("weaknesses")),
            # 是否下发总分由档位决定，不由模型决定
            overall_score=(
                _clamp_score(overall_score)
                if level == FEEDBACK_LEVEL_FULL
                else None
            ),
        )

    # ------------------------ 按简历匹配题目 ------------------------

    def match_questions_by_resume(
        self,
        resume_text: str,
        position_name: str,
        jd: str,
        dims: list[str],
        candidates: list[QuestionBrief],
        count: int,
    ) -> list[MatchedQuestion]:
        resume = (resume_text or "").strip()
        if not resume:
            # 调用方本应先判出「未关联简历」并整条路都不调用本方法
            raise AIProviderError("缺少简历内容，无法按简历匹配题目")
        if not dims:
            raise AIProviderError("缺少评估维度，无法按简历匹配题目")
        if count <= 0 or not candidates:
            return []

        # 池内 id 集合：解析阶段据此丢弃模型编造的 id（「只挑不生成」的第二层保证）
        pool = {item.question_id for item in candidates}
        listing = "\n".join(
            f"- question_id={item.question_id}｜维度：{item.dimension}"
            f"｜分类：{item.category}｜题干：{item.content}"
            for item in candidates
        )
        system = "你是一位资深面试官，负责从已有题库中挑选与候选人简历最相关的题目。"
        user = (
            f"岗位名称：{position_name}\n"
            f"岗位描述（JD）：\n{jd}\n\n"
            f"评估维度：{json.dumps(dims, ensure_ascii=False)}\n\n"
            f"候选人简历：\n{resume}\n\n"
            f"可选题目清单（question_id 只能取自以下清单）：\n{listing}\n\n"
            f"请从中挑选至多 {count} 道与简历最相关的题目，输出 JSON 数组，"
            "每个元素包含：\n"
            '- "question_id"：**必须是上面清单中的数值**，不得编造、不得改写\n'
            '- "reason"：匹配理由，说明与简历中的哪段经历相关\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=True)
        if not isinstance(raw, list):
            raise AIProviderError("AI 返回的简历匹配结果不是 JSON 数组")

        results: list[MatchedQuestion] = []
        seen: set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                question_id = int(item.get("question_id"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if question_id not in pool or question_id in seen:
                continue  # 池外 id 一律丢弃，绝不伪造
            seen.add(question_id)
            results.append(
                MatchedQuestion(
                    question_id=question_id,
                    reason=str(item.get("reason") or "").strip()
                    or _MATCH_FALLBACK_REASON,
                )
            )
            if len(results) >= count:
                break

        # 「没有」与「坏了」必须可区分：返回空数组是正当结论（确实没有相关题目），
        # 而非空数组却一条都没留下则是**输出不合格**。静默返 [] 会把 AI 故障
        # 伪装成正常结论，线上只剩「匹配不出来」这一种症状，无法定位。
        if raw and not results:
            raise AIProviderError("AI 返回的题目 id 均不在候选题库内")

        return results

    # ------------------------ 面试前准备提纲 ------------------------

    def generate_interview_prep(
        self,
        position_name: str,
        jd: str,
        dims: list[str],
        candidate_name: str,
        resume_text: str | None,
        questions: list[QuestionBrief],
    ) -> InterviewPrepResult:
        if not dims:
            raise AIProviderError("缺少评估维度，无法生成面试准备提纲")

        resume = (resume_text or "").strip()
        resume_block = resume or _NO_RESUME_TEXT
        questions_text = (
            "\n".join(
                f"- {item.content}（考察维度：{item.dimension}）" for item in questions
            )
            or _NO_QUESTIONS_TEXT
        )
        name = (candidate_name or "").strip() or "候选人"

        system = "你是一位资深面试官与招聘专家，正在为一场即将开始的面试准备提纲。"
        user = (
            f"岗位名称：{position_name}\n"
            f"岗位描述（JD）：\n{jd}\n\n"
            f"评估维度（dimension 只能从中选择）：{json.dumps(dims, ensure_ascii=False)}\n"
            f"候选人姓名：{name}\n\n"
            f"候选人简历：\n{resume_block}\n\n"
            f"本场已有题目：\n{questions_text}\n\n"
            "请生成面试准备提纲，输出 JSON 对象，字段：\n"
            '- "outline"：面试提纲，数组，每项含 "seq"（序号）、"phase"（阶段名）、'
            '"duration_min"（该阶段分钟数，正整数）、"notes"（该阶段要点）\n'
            '- "focus_points"：考察重点，数组，每项含 "dimension"（必须是给定维度之一）、'
            '"point"（应验证的能力项）、"reason"（为什么重点考察它）\n'
            '- "question_plan"：问题预案，数组，每项含 "question"（建议提问）、'
            '"intent"（考察意图）、"follow_ups"（可追问方向的**字符串数组**）\n'
            "要求：若存在简历，focus_points 中至少有一条与简历经历直接相关；"
            "若没有简历，不要凭空引用简历内容。\n"
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.3, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的面试准备提纲不是 JSON 对象")

        outline = self._parse_prep_outline(raw.get("outline"))
        focus_points = self._parse_prep_focus_points(raw.get("focus_points"), dims)
        question_plan = self._parse_prep_question_plan(raw.get("question_plan"))

        # 三部分任一为空即整批失败：缺了「考察重点」或「问题预案」的提纲不具备
        # 可用性，而重试成本只有一次点击。允许部分为空反而更糟 —— 前端会渲染出
        # 三块里空两块的面板，HR 无法判断是 AI 没生成还是本来就该空。
        if not outline or not focus_points or not question_plan:
            raise AIProviderError(
                "AI 返回的面试准备提纲不完整（提纲 / 考察重点 / 问题预案存在空项）"
            )

        return InterviewPrepResult(
            outline=outline, focus_points=focus_points, question_plan=question_plan
        )

    # -------------------- 简历与岗位匹配度评估 --------------------

    def evaluate_resume(
        self,
        position_name: str,
        jd: str,
        dims: list[str],
        resume_text: str,
    ) -> ResumeReviewResult:
        resume = (resume_text or "").strip()
        if not resume:
            # 调用方本应判出「未关联简历」并整条路都不调用本方法
            raise AIProviderError("缺少简历内容，无法评估简历与岗位的匹配度")
        if not dims:
            raise AIProviderError("缺少评估维度，无法评估简历与岗位的匹配度")

        system = (
            "你是一位资深招聘顾问，负责评估候选人的简历与目标岗位要求的匹配程度。"
            "你只描述**简历与岗位要求的重合度**：哪些对得上、哪些还缺。"
            "**不得**给出录用与否的建议，也不得评价候选人是否应该进入下一轮，"
            "措辞只针对简历本身。"
        )
        user = (
            f"岗位名称：{(position_name or '').strip() or _REVIEW_DEFAULT_POSITION}\n"
            f"岗位描述（JD）：\n{(jd or '').strip() or '（未提供）'}\n\n"
            f"评估维度：{json.dumps(dims, ensure_ascii=False)}\n\n"
            f"候选人简历：\n{resume}\n\n"
            "请评估该简历与这个岗位的匹配度，输出 JSON 对象，字段：\n"
            '- "match_score"：0–10 的数值，可带 1 位小数\n'
            '- "conclusion"：一段综合结论，只说重合度，**不得**含录用建议\n'
            f'- "strengths"：简历与岗位对得上的点，1–{RESUME_REVIEW_MAX_ITEMS} 条'
            "字符串，**不得为空**\n"
            f'- "gaps"：简历中缺失、建议补充的点，0–{RESUME_REVIEW_MAX_ITEMS} 条字符串\n'
            "只输出 JSON，不要任何解释文字。"
        )

        raw = self._request_json(system, user, temperature=0.2, expect_list=False)
        if not isinstance(raw, dict):
            raise AIProviderError("AI 返回的简历评估不是 JSON 对象")

        strengths = self._str_list(raw.get("strengths"))[:RESUME_REVIEW_MAX_ITEMS]
        if not strengths:
            # 与 Mock 同款前置（module-27 §3）：亮点为空说明这次评估没有产出可用
            # 内容。**不能**静默返回一份「没有亮点」的结论 —— 那会让「模型没答好」
            # 与「简历真的没有亮点」不可区分
            raise AIProviderError("AI 未给出任何简历亮点，本次评估不可用")

        return ResumeReviewResult(
            match_score=_clamp_score(raw.get("match_score")),
            conclusion=str(raw.get("conclusion") or "").strip()
            or _REVIEW_NO_CONCLUSION,
            strengths=strengths,
            gaps=self._str_list(raw.get("gaps"))[:RESUME_REVIEW_MAX_ITEMS],
        )

    @staticmethod
    def _parse_prep_outline(value: Any) -> list[PrepOutlineStage]:
        if not isinstance(value, list):
            return []

        stages: list[PrepOutlineStage] = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                continue
            phase = str(item.get("phase") or "").strip()
            if not phase:
                continue
            stages.append(
                PrepOutlineStage(
                    # seq 缺失时按数组下标补 1..n，保证顺序信息不丢
                    seq=OpenAIProvider._positive_int(item.get("seq"), index),
                    phase=phase,
                    duration_min=OpenAIProvider._positive_int(
                        item.get("duration_min"), _PREP_DEFAULT_DURATION_MIN
                    ),
                    notes=str(item.get("notes") or "").strip(),
                )
            )
        return stages

    @staticmethod
    def _parse_prep_focus_points(
        value: Any, dims: list[str]
    ) -> list[PrepFocusPoint]:
        if not isinstance(value, list):
            return []

        points: list[PrepFocusPoint] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            dimension = OpenAIProvider._coerce_dimension(item.get("dimension"), dims)
            if dimension is None:
                continue  # 无从判断归属维度，丢弃该条
            point = str(item.get("point") or "").strip()
            if not point:
                continue
            points.append(
                PrepFocusPoint(
                    dimension=dimension,
                    point=point,
                    reason=str(item.get("reason") or "").strip(),
                )
            )
        return points

    @staticmethod
    def _parse_prep_question_plan(value: Any) -> list[PrepQuestionItem]:
        if not isinstance(value, list):
            return []

        plan: list[PrepQuestionItem] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            plan.append(
                PrepQuestionItem(
                    question=question,
                    intent=str(item.get("intent") or "").strip(),
                    follow_ups=OpenAIProvider._str_list(item.get("follow_ups")),
                )
            )
        return plan

    @staticmethod
    def _positive_int(value: Any, fallback: int) -> int:
        """正整数校验；非数值 / 非正数一律回落 fallback。"""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return fallback
        return number if number > 0 else fallback
