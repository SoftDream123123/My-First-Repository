"""AI 能力契约：数据结构 + 抽象基类。

设计要点：本模块**只接收原始值**（字符串、列表），不接收任何 ORM 对象。
这保证 ai 不依赖 position / question / interview / evaluation 任何业务模块，
既守住了依赖单向，也让 Mock 实现可以在完全不起数据库的情况下被单测。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# 评分区间（PRD §4.5：逐题分、维度分、总分均 0–10）
SCORE_MIN = 0.0
SCORE_MAX = 10.0

# 难度取值
DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"
DIFFICULTIES = (DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD)

# 来源取值（PRD §5.2）
SOURCE_BANK = "bank"
SOURCE_AI = "ai"

# 题型取值（PRD §4.3）
QUESTION_TYPE_SINGLE_CHOICE = "single_choice"
QUESTION_TYPE_SHORT_ANSWER = "short_answer"
QUESTION_TYPES = (QUESTION_TYPE_SINGLE_CHOICE, QUESTION_TYPE_SHORT_ANSWER)

# 候选人反馈档位（PRD §4.9）
#   summary → 仅综合结论 / 优点 / 待改进，不下发总分（默认）
#   full    → 额外下发总分；逐题分与维度分在任何档位都不下发
FEEDBACK_LEVEL_SUMMARY = "summary"
FEEDBACK_LEVEL_FULL = "full"
FEEDBACK_LEVELS = (FEEDBACK_LEVEL_SUMMARY, FEEDBACK_LEVEL_FULL)

# 判分及格线 —— **全项目唯一**，practice 与 evaluation 都必须用它，不另定义。
#
# 前端 components/shell.js 的 scoreClass() 与 components/radar.js 的 isPass
# 也用 6.5，但那两处是独立的 JS 实现（前端无法 import 后端常量）。若这里改成
# 别的值，必须同步改前端，否则会出现「刷题判你答对了，报告页却显示需关注」。
PASS_THRESHOLD = 6.5


@dataclass
class QAPair:
    """一道题的维度、题干与回答。未作答时 answer 为 None。"""

    dimension: str
    question: str
    answer: str | None


@dataclass
class GeneratedQuestion:
    content: str
    dimension: str
    difficulty: str = DIFFICULTY_MEDIUM
    category: str = "通用"
    tags: list[str] = field(default_factory=list)
    source: str = SOURCE_AI


@dataclass
class QuestionScoreResult:
    score: float
    comment: str


@dataclass
class DimensionScoreResult:
    dimension: str
    score: float
    comment: str


@dataclass
class ReportResult:
    overall_score: float
    conclusion: str
    strengths: list[str]
    weaknesses: list[str]


@dataclass
class ReferenceAnswerResult:
    """一题的参考答案与解析。

    单选题的 reference_answer 是某个选项的**完整文本**（不是下标）——
    选项可被重排，存文本则重排后答案仍然正确。
    """

    reference_answer: str
    explanation: str


@dataclass
class PracticeGradeResult:
    """刷题作答的判分结果。

    score 与 is_correct 由 Provider 一并算出，保证两者自洽 ——
    否则调用方会各自用不同阈值推导 is_correct，出现第二个判据。
    """

    score: float
    is_correct: bool
    explanation: str


@dataclass
class CandidateFeedbackResult:
    """面向候选人的脱敏反馈。

    level='summary' 时 overall_score 为 None —— 由 Provider 按 level 决定，
    而不是由调用方决定是否下发（见 module-11 §4.3）。
    """

    conclusion: str
    strengths: list[str]
    weaknesses: list[str]
    overall_score: float | None


class AIProvider(ABC):
    """AI 能力抽象基类。

    七个方法覆盖两条业务线：
      · HR 侧：出题 → 逐题评分 → 多维评分 → 汇总报告
      · 候选人侧：补参考答案 / 刷题判分 / 候选人脱敏反馈

    全部方法**只接收原始值**（str / list[str] / float），不接收 ORM 对象。
    """

    @abstractmethod
    def generate_questions(
        self,
        position_name: str,
        jd: str,
        dims: list[str],
        existing_contents: list[str],
        count: int,
    ) -> list[GeneratedQuestion]:
        """按岗位 JD + 评估维度生成 count 道新题，且不与 existing_contents 重复。"""

    @abstractmethod
    def evaluate_answer(
        self, dimension: str, question: str, answer: str | None
    ) -> QuestionScoreResult:
        """对单题回答打分并给出评语。"""

    @abstractmethod
    def evaluate_dimensions(
        self, dims: list[str], qa_pairs: list[QAPair]
    ) -> list[DimensionScoreResult]:
        """逐维度打分。返回顺序必须与 dims 一致。"""

    @abstractmethod
    def summarize_report(
        self,
        dims: list[str],
        dimension_scores: list[DimensionScoreResult],
        question_scores: list[QuestionScoreResult],
    ) -> ReportResult:
        """汇总总分、结论、优点与待改进。"""

    @abstractmethod
    def generate_reference_answer(
        self,
        question_type: str,
        content: str,
        options: list[str],
        dimension: str,
    ) -> ReferenceAnswerResult:
        """为一题生成参考答案与解析。

        单选题返回的答案**必须是 options 中的一项**。若模型给出选项外的文本，
        本层原样返回、不做「吸附到最接近的选项」——那等于伪造正确答案；
        由 question.service 判定并报 409（见 module-10 §5.2）。
        """

    @abstractmethod
    def grade_practice_answer(
        self,
        question_type: str,
        content: str,
        reference_answer: str,
        user_answer: str,
    ) -> PracticeGradeResult:
        """对刷题作答判分并给出解析。

        question_type 参数即使 practice 对单选题不走本方法也保留：真实 Provider
        可据此定制 prompt，调用方也无需在调用点做分支假设。

        注意：单选题的判分职责在 practice（本地规则，不消耗 AI），
        本方法的单选分支只是防御性实现。
        """

    @abstractmethod
    def generate_candidate_feedback(
        self,
        level: str,
        conclusion: str,
        strengths: list[str],
        weaknesses: list[str],
        overall_score: float,
    ) -> CandidateFeedbackResult:
        """由报告结论生成面向候选人的脱敏反馈。

        level 同时决定返回的 overall_score 是否为 None：
        'summary' → None（默认档，候选人看不到分数）；'full' → 保留原值。
        未知 level 一律按 'summary' 处理 —— 给得更少是安全方向。
        """
