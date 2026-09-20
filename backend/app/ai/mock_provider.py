"""Mock Provider：基于规则的**确定性**实现。

核心要求：相同输入必须产生完全相同输出 —— 不允许任何随机性、时间戳或
字典序依赖。这是 Mock 能作为自动化测试基准的前提。
"""

import logging
import re

from app.ai.base import (
    DIFFICULTIES,
    FEEDBACK_LEVEL_FULL,
    FEEDBACK_LEVEL_SUMMARY,
    FEEDBACK_LEVELS,
    PASS_THRESHOLD,
    QUESTION_TYPE_SINGLE_CHOICE,
    SCORE_MAX,
    SCORE_MIN,
    SOURCE_AI,
    AIProvider,
    CandidateFeedbackResult,
    DimensionScoreResult,
    GeneratedQuestion,
    PracticeGradeResult,
    QAPair,
    QuestionScoreResult,
    ReferenceAnswerResult,
    ReportResult,
)
from app.core.exceptions import AIProviderError

logger = logging.getLogger(__name__)

_DIGIT_RE = re.compile(r"\d")

_QUESTION_TEMPLATES = (
    "关于{dim}：请描述一次你在{position}相关工作中遇到的具体挑战，以及你的处理方式。",
    "关于{dim}：如果让你从零开始改进{position}岗位的一项关键流程，你会怎么做？",
    "关于{dim}：请举例说明你如何衡量自己在{dim}方面的表现。",
)

# 参考答案模板：按题干长度取模选择，保证「同输入必得同输出」
_REFERENCE_TEMPLATES = (
    "围绕{dim}，一份合格的回答应当先交代背景与目标，再说明你采取的具体做法，"
    "最后给出可量化的结果。参考要点：{snippet}……",
    "就{dim}而言，理想的回答需要覆盖三个层次：现状判断、行动方案，"
    "以及事后的复盘与改进。参考要点：{snippet}……",
    "回答{dim}类问题时建议以「情境—任务—行动—结果」的结构展开，"
    "并突出你本人在其中的独立贡献。参考要点：{snippet}……",
)

_REFERENCE_EXPLANATIONS = (
    "本题考察{dim}。评分关注是否给出了具体事例、可否验证其结果，"
    "以及表述是否有条理。",
    "本题考察{dim}。只给结论而缺少过程与结果的回答，通常难以获得高分。",
)

_REFERENCE_SNIPPET_LEN = 20

_FEEDBACK_PREFIX = "感谢你参与本次面试。以下是本次面试的反馈，供你参考："

# 具体化标记 → 各 +0.5 分
_BONUS_MARKERS = (r"\d", r"%|百分比", r"项目|案例", r"例如|比如")
_BONUS_PER_MARKER = 0.5
_BONUS_CAP = 1.5


def _round1(value: float) -> float:
    """保留 1 位小数并夹到 [0, 10]。"""
    return round(min(max(value, SCORE_MIN), SCORE_MAX), 1)


def _bigrams(text: str) -> set[str]:
    """字符二元组集合。

    先去空白再切分：中文没有词边界，不做分词；长度不足 2 时退化为单字符集合。
    """
    normalized = re.sub(r"\s+", "", text)
    if len(normalized) < 2:
        return set(normalized)
    return {normalized[i : i + 2] for i in range(len(normalized) - 1)}


def _similarity(left: str, right: str) -> float:
    """字符二元组的 Jaccard 相似度 = |A ∩ B| / |A ∪ B|。并集为空时返回 0。"""
    a, b = _bigrams(left), _bigrams(right)
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class MockProvider(AIProvider):
    """规则驱动的确定性 Provider。"""

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

        taken = set(existing_contents)
        results: list[GeneratedQuestion] = []

        for i in range(count):
            dimension = dims[i % len(dims)]
            template = _QUESTION_TEMPLATES[i % len(_QUESTION_TEMPLATES)]
            content = template.format(dim=dimension, position=position_name)

            # 确定性去重：撞车则追加「（变体N）」，N 从 1 递增
            variant = 1
            while content in taken:
                content = (
                    template.format(dim=dimension, position=position_name)
                    + f"（变体{variant}）"
                )
                variant += 1
            taken.add(content)

            results.append(
                GeneratedQuestion(
                    content=content,
                    dimension=dimension,
                    difficulty=DIFFICULTIES[i % len(DIFFICULTIES)],
                    category="通用",
                    tags=[dimension],
                    source=SOURCE_AI,
                )
            )

        return results

    # -------------------------- 逐题评分 --------------------------

    def evaluate_answer(
        self, dimension: str, question: str, answer: str | None
    ) -> QuestionScoreResult:
        text = (answer or "").strip()

        if not text:
            return QuestionScoreResult(
                score=0.0, comment=f"未作答，{dimension}维度无法评估。"
            )

        score = self._base_score(len(text))
        score += self._bonus(text)
        score = _round1(score)

        return QuestionScoreResult(score=score, comment=self._answer_comment(dimension, score))

    @staticmethod
    def _base_score(length: int) -> float:
        if length < 20:
            return 3.0
        if length < 100:
            return 5.0
        if length < 300:
            return 7.0
        return 8.5

    @staticmethod
    def _bonus(text: str) -> float:
        hits = sum(1 for pattern in _BONUS_MARKERS if re.search(pattern, text))
        return min(hits * _BONUS_PER_MARKER, _BONUS_CAP)

    @staticmethod
    def _answer_comment(dimension: str, score: float) -> str:
        if score <= 0.0:
            return f"未作答，{dimension}维度无法评估。"
        if score < 5.0:
            return f"回答较简略，尚未体现出{dimension}方面的具体经验。"
        if score < 8.0:
            return (
                f"回答基本切题，在{dimension}方面有一定体现，"
                "建议补充更多细节与量化结果。"
            )
        return f"回答详实，{dimension}方面有清晰的具体事例支撑，表达有条理。"

    # -------------------------- 多维评分 --------------------------

    def evaluate_dimensions(
        self, dims: list[str], qa_pairs: list[QAPair]
    ) -> list[DimensionScoreResult]:
        results: list[DimensionScoreResult] = []

        for dim in dims:
            scores = [
                self.evaluate_answer(dim, pair.question, pair.answer).score
                for pair in qa_pairs
                if pair.dimension == dim
            ]

            if not scores:
                results.append(
                    DimensionScoreResult(
                        dimension=dim,
                        score=0.0,
                        comment="该维度在本次面试中无对应题目。",
                    )
                )
                continue

            score = _round1(sum(scores) / len(scores))
            results.append(
                DimensionScoreResult(
                    dimension=dim, score=score, comment=self._dimension_comment(dim, score)
                )
            )

        return results

    @staticmethod
    def _dimension_comment(dimension: str, score: float) -> str:
        if score <= 0.0:
            return "该维度在本次面试中无对应题目。"
        if score < 5.0:
            return f"{dimension}维度表现偏弱，建议在后续轮次中重点考察。"
        if score < 8.0:
            return f"{dimension}维度表现中等，基本达到岗位要求。"
        return f"{dimension}维度表现突出，是本次面试的加分项。"

    # -------------------------- 汇总报告 --------------------------

    def summarize_report(
        self,
        dims: list[str],
        dimension_scores: list[DimensionScoreResult],
        question_scores: list[QuestionScoreResult],
    ) -> ReportResult:
        if not dimension_scores:
            return ReportResult(
                overall_score=0.0,
                conclusion="本次面试缺少有效作答，无法形成评估结论。",
                strengths=["本次面试暂无明显优势维度"],
                weaknesses=["本次面试暂无明显薄弱维度"],
            )

        overall = _round1(
            sum(item.score for item in dimension_scores) / len(dimension_scores)
        )

        strengths = [
            f"{item.dimension}（{item.score:.1f}）：表现较好"
            for item in dimension_scores
            if item.score >= PASS_THRESHOLD
        ]
        weaknesses = [
            f"{item.dimension}（{item.score:.1f}）：有待提升"
            for item in dimension_scores
            if item.score < PASS_THRESHOLD
        ]

        return ReportResult(
            overall_score=overall,
            conclusion=self._conclusion(overall),
            strengths=strengths or ["本次面试暂无明显优势维度"],
            weaknesses=weaknesses or ["本次面试暂无明显薄弱维度"],
        )

    @staticmethod
    def _conclusion(overall: float) -> str:
        if overall <= 0.0:
            return "本次面试缺少有效作答，无法形成评估结论。"
        if overall < 4.0:
            return "整体表现未达预期，建议暂不推进。"
        if overall < 6.0:
            return "整体表现一般，建议针对薄弱维度追加考察。"
        if overall < 8.0:
            return "整体表现良好，建议结合岗位要求综合评估。"
        return "整体表现优秀，建议进入下一轮。"

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
                # 调用方本应在 schema 层拦住；此处是防御性失败
                raise AIProviderError("缺少选项，无法生成参考答案")

            index = len(content) % len(options)
            return ReferenceAnswerResult(
                reference_answer=options[index],
                explanation=(
                    f"正确答案是选项中的第 {index + 1} 项，"
                    f"它在{dimension}维度上最贴合题干要求。"
                ),
            )

        snippet = content[:_REFERENCE_SNIPPET_LEN]
        return ReferenceAnswerResult(
            reference_answer=_REFERENCE_TEMPLATES[
                len(content) % len(_REFERENCE_TEMPLATES)
            ].format(dim=dimension, snippet=snippet),
            explanation=_REFERENCE_EXPLANATIONS[
                len(content) % len(_REFERENCE_EXPLANATIONS)
            ].format(dim=dimension),
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

        # 空作答短路：两个实现必须一致，且不发网络请求
        if not text:
            return PracticeGradeResult(
                score=SCORE_MIN, is_correct=False, explanation="未作答"
            )

        reference = (reference_answer or "").strip()

        if question_type == QUESTION_TYPE_SINGLE_CHOICE:
            is_correct = text == reference
            return PracticeGradeResult(
                score=SCORE_MAX if is_correct else SCORE_MIN,
                is_correct=is_correct,
                explanation=(
                    "回答正确。"
                    if is_correct
                    else f"回答不正确。正确答案：{reference}"
                ),
            )

        if not reference:
            # practice 在调用前就应判出这种情况并标记未判分（见 module-13 §5.2）
            raise AIProviderError("该题缺少参考答案，无法判分")

        score = round(10 * _similarity(reference, text), 1)
        return PracticeGradeResult(
            score=score,
            is_correct=score >= PASS_THRESHOLD,
            explanation=self._practice_explanation(score),
        )

    @staticmethod
    def _practice_explanation(score: float) -> str:
        if score >= 8.0:
            return "回答与参考答案高度吻合，要点覆盖完整。"
        if score >= PASS_THRESHOLD:
            return "回答覆盖了主要要点，个别细节仍可补充。"
        if score > 0.0:
            return "回答与参考答案的要点重合较少，建议对照参考答案补充关键内容。"
        return "回答与参考答案没有重合，建议重新作答。"

    # ------------------------ 候选人反馈 ------------------------

    def generate_candidate_feedback(
        self,
        level: str,
        conclusion: str,
        strengths: list[str],
        weaknesses: list[str],
        overall_score: float,
    ) -> CandidateFeedbackResult:
        if level not in FEEDBACK_LEVELS:
            # 退化为 summary 是「给得更少」这一安全方向，但配置写错必须留痕
            logger.warning("未知的候选人反馈档位 %r，已按 summary 处理", level)
            level = FEEDBACK_LEVEL_SUMMARY

        return CandidateFeedbackResult(
            conclusion=f"{_FEEDBACK_PREFIX}{conclusion.strip()}",
            # 只 strip，不改变条目数量与顺序 —— 便于 HR 与候选人逐条对照
            strengths=[item.strip() for item in strengths],
            weaknesses=[item.strip() for item in weaknesses],
            overall_score=(
                _round1(overall_score)
                if level == FEEDBACK_LEVEL_FULL
                else None
            ),
        )
