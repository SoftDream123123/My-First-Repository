"""Mock Provider：基于规则的**确定性**实现。

核心要求：相同输入必须产生完全相同输出 —— 不允许任何随机性、时间戳或
字典序依赖。这是 Mock 能作为自动化测试基准的前提。
"""

import re

from app.ai.base import (
    DIFFICULTIES,
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
from app.core.exceptions import AIProviderError

_DIGIT_RE = re.compile(r"\d")

_QUESTION_TEMPLATES = (
    "关于{dim}：请描述一次你在{position}相关工作中遇到的具体挑战，以及你的处理方式。",
    "关于{dim}：如果让你从零开始改进{position}岗位的一项关键流程，你会怎么做？",
    "关于{dim}：请举例说明你如何衡量自己在{dim}方面的表现。",
)

# 具体化标记 → 各 +0.5 分
_BONUS_MARKERS = (r"\d", r"%|百分比", r"项目|案例", r"例如|比如")
_BONUS_PER_MARKER = 0.5
_BONUS_CAP = 1.5

# 优势 / 待改进的分档阈值
_STRENGTH_THRESHOLD = 6.5


def _round1(value: float) -> float:
    """保留 1 位小数并夹到 [0, 10]。"""
    return round(min(max(value, SCORE_MIN), SCORE_MAX), 1)


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
            if item.score >= _STRENGTH_THRESHOLD
        ]
        weaknesses = [
            f"{item.dimension}（{item.score:.1f}）：有待提升"
            for item in dimension_scores
            if item.score < _STRENGTH_THRESHOLD
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
