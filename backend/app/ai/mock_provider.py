"""Mock Provider：基于规则的**确定性**实现。

核心要求：相同输入必须产生完全相同输出 —— 不允许任何随机性、时间戳或
字典序依赖。这是 Mock 能作为自动化测试基准的前提。
"""

import logging
import re

from app.ai.base import (
    CANDIDATE_FEEDBACK_LEAD,
    DIFFICULTIES,
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

# 没有明显强项 / 弱项时的两句兜底，保证结论读起来是完整的一句
_FEEDBACK_NO_STRONG = "各个维度上还没有体现出明显突出的部分"
_FEEDBACK_NO_WEAK = "各维度表现比较均衡，没有明显短板"


def _candidate_conclusion(dimension_scores: list[DimensionScoreResult]) -> str:
    """由维度得分重写一句**面向候选人本人**的综合结论。

    只点出强项与弱项**是哪几个维度**，理由交给报告里那两条优缺点列表 ——
    结论里再复述一遍理由，会和紧接着的条目逐字重复，读起来像同一句话说了两遍。

    判强弱的阈值用 `PASS_THRESHOLD`，与 `summarize_report` 同一把尺；
    调用方因此不必自己再算一套「哪些算强项」。
    """
    strong = [
        item.dimension for item in dimension_scores if item.score >= PASS_THRESHOLD
    ]
    weak = [
        item.dimension for item in dimension_scores if item.score < PASS_THRESHOLD
    ]

    good = (
        f"你在{'、'.join(strong)}上的表现比较扎实"
        if strong
        else _FEEDBACK_NO_STRONG
    )
    gap = (
        f"{'、'.join(weak)}是还需要补强的地方" if weak else _FEEDBACK_NO_WEAK
    )
    return f"{CANDIDATE_FEEDBACK_LEAD}{good}，{gap}。"

# ---- 按简历匹配（module-18 §4.1）----
#
# 打分权重：维度命中 > 题干重合 > 分类命中。维度是岗位的考察口径，最可信；
# 分类较粗（「通用」这类），因此权重最低。
_MATCH_WEIGHT_DIMENSION = 3.0
_MATCH_WEIGHT_CATEGORY = 1.5
_MATCH_WEIGHT_OVERLAP = 2.0

# 仅用于 reason 的措辞分档，**不参与排序**（排序用连续分数），因此取值敏感性低。
_MATCH_OVERLAP_MIN = 0.3

_MATCH_REASON_HIGH = "简历中体现了{dim}相关经历，且本题题干与其表述有重合，属于高相关题目。"
_MATCH_REASON_DIMENSION = "简历中体现了{dim}相关经历，本题直接考察该维度。"
_MATCH_REASON_CATEGORY = "简历中的{category}方向与本题一致。"
_MATCH_REASON_OVERLAP = "本题题干与简历表述有一定重合。"
_MATCH_REASON_GENERIC = "本题与岗位评估维度相关，作为通用考察项。"

# ---- 面试前准备（module-18 §4.2）----

_PREP_DEFAULT_CANDIDATE = "候选人"
_PREP_RESUME_SNIPPET_LEN = 40
_PREP_MAX_QUESTIONS = 4

_PREP_RESUME_FOCUS_DIMENSION = "简历核对"

_PREP_FOCUS_TEMPLATES = (
    ("重点验证{dim}的真实水平", "若只有结论而缺少过程，很难判断其实际深度。"),
    ("确认{dim}相关的具体案例", "要求给出可核对的项目、数据或结果，避免泛泛而谈。"),
    ("考察{dim}在压力下的表现", "追问失败或冲突场景，观察其复盘与改进方式。"),
)

_PREP_INTENT_TEMPLATES = (
    "考察{dim}：是否具备与岗位要求相匹配的实际经验。",
    "考察{dim}：判断其在该维度上的深度与边界。",
    "考察{dim}：验证其判断依据是否可复核。",
)

_PREP_FOLLOW_UP_TEMPLATES = (
    ("如果重来一次，你会怎么做？", "这个结果是如何量化的？"),
    ("当时还有哪些方案？为什么没有选它们？", "过程中最大的阻力是什么？"),
    ("这件事里你的独立贡献是什么？", "后续有没有做复盘与改进？"),
)

_PREP_SUGGEST_TEMPLATE = "关于{dim}：请结合一段具体经历，谈谈你的做法与最终结果。"

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


def _resume_overlap(question_text: str, resume_text: str) -> float:
    """题干二元组**被简历覆盖**的比例 = |A ∩ B| / |A|（A = 题干，B = 简历）。

    刻意**不复用 `_similarity`（Jaccard）**：Jaccard 的分母是并集，而简历可达
    2 万字、题干只有几十字，并集被简历完全主导，相似度会塌到 1e-3 量级 ——
    任何阈值都失去分辨力，等于这个信号不存在。以题干自身大小作分母，量级稳定
    在 [0, 1]，语义清晰：「这道题的用词有多大比例出现在简历里」。

    刷题判分能用 Jaccard，是因为参考答案与考生作答的长度量级相当；
    简历匹配不是同一场景，因此不共用同一个函数。
    """
    question_grams = _bigrams(question_text)
    if not question_grams:
        return 0.0
    return len(question_grams & _bigrams(resume_text)) / len(question_grams)


# 简历评估的结论分档。四档说的**都是「简历与岗位的重合度」，不是「要不要这个人」**
# —— 任何档位都不得出现去留判断（PRD §4.9 的红线，§4.15 明确沿用）。
# 档位边界用 PASS_THRESHOLD，与 summarize_report 同一把尺，避免出现
# 「面试 6.5 算过、简历 6.5 算不过」这种内部不一致。
_REVIEW_BANDS = (
    (8.0, "简历与岗位要求的重合度高，多个评估维度都能在简历中找到对应的经历。"),
    (
        PASS_THRESHOLD,
        "简历与岗位要求有较好重合，个别维度可以再补一些具体事例与成果。",
    ),
    (4.0, "简历与岗位要求部分重合，若干维度还缺少可对应的经历描述。"),
    (SCORE_MIN, "简历与该岗位要求的重合较少，建议按岗位维度补充相关经历与成果。"),
)

_REVIEW_STRENGTH_TEMPLATE = "简历中体现了「{dim}」相关经历"
_REVIEW_GAP_TEMPLATE = "简历中未见「{dim}」相关经历，建议补充具体事例"
# strengths 不允许为空（PRD §4.15）：一个维度都没命中时兜这一条，
# 否则「评分坏了」与「简历真的差」会不可区分
_REVIEW_FALLBACK_STRENGTH = "简历整体表述完整、可读性良好"


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

        # 条目不内嵌维度分：这些条目会**原样**进入候选人可见的脱敏反馈
        #（PRD §4.9「便于两处逐条对照」），而 §4.9 同时规定默认不下发维度分。
        # 分数留在 dimension_score 表里供 HR 端雷达图使用。
        strengths = [
            f"{item.dimension}：表现较好"
            for item in dimension_scores
            if item.score >= PASS_THRESHOLD
        ]
        weaknesses = [
            f"{item.dimension}：有待提升"
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
        overall_score: float,
        strengths: list[str],
        weaknesses: list[str],
        dimension_scores: list[DimensionScoreResult],
    ) -> CandidateFeedbackResult:
        if level not in FEEDBACK_LEVELS:
            # 退化为 summary 是「给得更少」这一安全方向，但配置写错必须留痕
            logger.warning("未知的候选人反馈档位 %r，已按 summary 处理", level)
            level = FEEDBACK_LEVEL_SUMMARY

        return CandidateFeedbackResult(
            # 由维度得分**重写**，不是报告结论的复述 —— 报告那句含去留判断（PRD §4.9）
            conclusion=_candidate_conclusion(dimension_scores),
            # 只 strip，不改变条目数量与顺序 —— 便于 HR 与候选人逐条对照
            strengths=[item.strip() for item in strengths],
            weaknesses=[item.strip() for item in weaknesses],
            overall_score=(
                _round1(overall_score)
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
            # 调用方本应判出「未关联简历」并整条路都不调用本方法
            raise AIProviderError("缺少简历内容，无法按简历匹配题目")
        if not dims:
            raise AIProviderError("缺少评估维度，无法按简历匹配题目")
        if count <= 0 or not candidates:
            return []

        scored = []
        for item in candidates:
            dim_hit = item.dimension in resume
            cat_hit = item.category in resume
            overlap = _resume_overlap(item.content, resume)
            score = (
                _MATCH_WEIGHT_DIMENSION * dim_hit
                + _MATCH_WEIGHT_CATEGORY * cat_hit
                + _MATCH_WEIGHT_OVERLAP * overlap
            )
            scored.append((score, item, dim_hit, cat_hit, overlap))

        # 同分必须有序：按 question_id 升序兜底，否则结果会依赖传入顺序。
        scored.sort(key=lambda row: (-row[0], row[1].question_id))

        return [
            MatchedQuestion(
                question_id=item.question_id,
                reason=self._match_reason(item, dim_hit, cat_hit, overlap),
            )
            for _score, item, dim_hit, cat_hit, overlap in scored[:count]
        ]

    @staticmethod
    def _match_reason(
        item: QuestionBrief, dim_hit: bool, cat_hit: bool, overlap: float
    ) -> str:
        if dim_hit and overlap >= _MATCH_OVERLAP_MIN:
            return _MATCH_REASON_HIGH.format(dim=item.dimension)
        if dim_hit:
            return _MATCH_REASON_DIMENSION.format(dim=item.dimension)
        if cat_hit:
            return _MATCH_REASON_CATEGORY.format(category=item.category)
        if overlap >= _MATCH_OVERLAP_MIN:
            return _MATCH_REASON_OVERLAP
        return _MATCH_REASON_GENERIC

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

        name = (candidate_name or "").strip() or _PREP_DEFAULT_CANDIDATE
        resume = (resume_text or "").strip()

        return InterviewPrepResult(
            outline=self._prep_outline(name, dims, has_resume=bool(resume)),
            focus_points=self._prep_focus_points(dims, resume),
            question_plan=self._prep_question_plan(dims, questions),
        )

    @staticmethod
    def _prep_outline(
        candidate_name: str, dims: list[str], has_resume: bool
    ) -> list[PrepOutlineStage]:
        """固定四阶段、合计 45 分钟；只有 notes 随输入变化。

        时长硬编码：Mock 的职责是确定性与可演示，不是拟真 ——
        真实 Provider 由模型按岗位自定。
        """
        if has_resume:
            experience_notes = (
                "围绕简历中的项目经历逐段核对，确认其本人在项目中的"
                "实际职责与产出。"
            )
        else:
            experience_notes = (
                "候选人未提供简历，改为围绕岗位要求做开放式了解，"
                "注意记录可核对的事实。"
            )

        return [
            PrepOutlineStage(
                seq=1,
                phase="开场与自我介绍",
                duration_min=5,
                notes=f"请{candidate_name}做自我介绍，建立基本印象。",
            ),
            PrepOutlineStage(
                seq=2, phase="经历核对", duration_min=10, notes=experience_notes
            ),
            PrepOutlineStage(
                seq=3,
                phase="能力考察",
                duration_min=20,
                notes=(
                    f"按评估维度逐项验证：{'、'.join(dims)}。"
                    "每个维度至少准备一个可追问的具体问题。"
                ),
            ),
            PrepOutlineStage(
                seq=4,
                phase="候选人提问与收尾",
                duration_min=10,
                notes="留出时间回答候选人的提问，并说明后续流程与时间安排。",
            ),
        ]

    @staticmethod
    def _prep_focus_points(dims: list[str], resume: str) -> list[PrepFocusPoint]:
        """每个维度一条（模板按索引取模），有简历时额外追加一条「简历核对」。"""
        points = [
            PrepFocusPoint(
                dimension=dim,
                point=_PREP_FOCUS_TEMPLATES[index % len(_PREP_FOCUS_TEMPLATES)][0].format(
                    dim=dim
                ),
                reason=_PREP_FOCUS_TEMPLATES[index % len(_PREP_FOCUS_TEMPLATES)][1],
            )
            for index, dim in enumerate(dims)
        ]

        if resume:
            snippet = resume[:_PREP_RESUME_SNIPPET_LEN]
            points.append(
                PrepFocusPoint(
                    dimension=_PREP_RESUME_FOCUS_DIMENSION,
                    point="核对简历经历的真实性",
                    reason=(
                        f"简历中提到「{snippet}」，请确认其本人在其中的实际贡献。"
                    ),
                )
            )

        return points

    @staticmethod
    def _prep_question_plan(
        dims: list[str], questions: list[QuestionBrief]
    ) -> list[PrepQuestionItem]:
        """先纳入本场已有题目，再用维度建议补足到 4 条。

        先取已有题目：那些是 HR 已经决定要问的，问题预案把它们纳入才
        「和这场面试对得上」。上限 4 条是产品判断 —— 45 分钟的提纲里塞
        10 个问题预案没有可执行性。
        """
        plan: list[PrepQuestionItem] = [
            PrepQuestionItem(
                question=item.content,
                intent=_PREP_INTENT_TEMPLATES[
                    index % len(_PREP_INTENT_TEMPLATES)
                ].format(dim=item.dimension),
                follow_ups=list(
                    _PREP_FOLLOW_UP_TEMPLATES[index % len(_PREP_FOLLOW_UP_TEMPLATES)]
                ),
            )
            for index, item in enumerate(questions[:_PREP_MAX_QUESTIONS])
        ]

        # dims 非空（方法入口已校验），因此循环必然能补满
        index = 0
        while len(plan) < _PREP_MAX_QUESTIONS:
            dim = dims[index % len(dims)]
            plan.append(
                PrepQuestionItem(
                    question=_PREP_SUGGEST_TEMPLATE.format(dim=dim),
                    intent=_PREP_INTENT_TEMPLATES[
                        index % len(_PREP_INTENT_TEMPLATES)
                    ].format(dim=dim),
                    follow_ups=list(
                        _PREP_FOLLOW_UP_TEMPLATES[
                            index % len(_PREP_FOLLOW_UP_TEMPLATES)
                        ]
                    ),
                )
            )
            index += 1

        return plan

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

        # 命中判定用**子串**（与 `match_questions_by_resume` 的维度命中同一惯用法），
        # 而不是 `_resume_overlap > 0`：三个维度常共享后缀（「沟通能力」「专业能力」
        # 共享「能力」二字），按二元组覆盖率判，没提到「专业能力」的简历也会拿到
        # 1/3 的「假命中」，gaps 就永远列不出这一条。先去空白再判，免得维度名被
        # 简历里的换行拆开而漏掉。
        compact = re.sub(r"\s+", "", resume)
        hits = [(dim, dim in compact) for dim in dims]
        hit_count = sum(1 for _dim, hit in hits if hit)
        dim_ratio = hit_count / len(dims)

        # JD 作为补充语境参与打分，权重 1/3：**评估依据的主体是评估维度**
        # （PRD §4.15 的前置条件正是「岗位已定义评估维度」）。JD 里与简历重合的
        # 词天然偏少，给它同等权重会把分数结构性地压低。JD 为空时只用维度。
        basis = (jd or "").strip()
        if basis:
            ratio = (dim_ratio * 2 + _resume_overlap(basis, resume)) / 3
        else:
            ratio = dim_ratio

        score = _round1(SCORE_MIN + ratio * (SCORE_MAX - SCORE_MIN))
        score = min(max(score, SCORE_MIN), SCORE_MAX)

        # 命中与未命中都按**岗位维度的原有顺序**列出（不排序），这样两份输出
        # 对同一岗位总是同一个次序，读起来可逐条对照
        strengths = [
            _REVIEW_STRENGTH_TEMPLATE.format(dim=dim)
            for dim, hit in hits
            if hit
        ][:RESUME_REVIEW_MAX_ITEMS] or [_REVIEW_FALLBACK_STRENGTH]
        gaps = [
            _REVIEW_GAP_TEMPLATE.format(dim=dim)
            for dim, hit in hits
            if not hit
        ][:RESUME_REVIEW_MAX_ITEMS]

        return ResumeReviewResult(
            match_score=score,
            conclusion=self._review_conclusion(score),
            strengths=strengths,
            gaps=gaps,
        )

    @staticmethod
    def _review_conclusion(score: float) -> str:
        for threshold, text in _REVIEW_BANDS:
            if score >= threshold:
                return text
        # _REVIEW_BANDS 的最后一档以 SCORE_MIN 收口，此分支不可达
        return _REVIEW_BANDS[-1][1]
