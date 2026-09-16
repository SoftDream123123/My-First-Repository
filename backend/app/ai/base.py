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


class AIProvider(ABC):
    """AI 能力抽象基类。

    四个方法覆盖「出题 → 逐题评分 → 多维评分 → 汇总报告」全流程。
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
