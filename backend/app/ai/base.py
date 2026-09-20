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

# 面向候选人的反馈开头。两个 Provider 共用一句 —— 它是这份文案的语气，不是某个
# Provider 的实现细节。**真实 Provider 生成不出结论时也用它兜底**：宁可兜一句
# 没有信息量的话，也不能退回报告那句结论，那里面含去留判断（PRD §4.9）。
CANDIDATE_FEEDBACK_LEAD = "感谢你参与本次面试。以下是本次面试的反馈，供你参考。"

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


@dataclass
class QuestionBrief:
    """题目的精简形态 —— 两个简历驱动方法（匹配 / 准备提纲）共用。

    名字刻意用中性的 `Brief` 而非 `Candidate`：本项目中 `Candidate` 专指
    候选人（candidate 角色、candidate_name），拿它命名题库题目会造成严重误读。
    `prep` 的需求（题干 + 维度）是 `match` 需求（再加 id + 分类）的子集，
    因此共用一个 dataclass，不另建只少两个字段的第二份。
    """

    question_id: int
    content: str
    dimension: str
    category: str


@dataclass
class MatchedQuestion:
    """按简历匹配到的题目。

    **只有 id 与理由，没有题面字段** —— 这让「编造一道题库外的新题」在
    结构上无从表达（即使模型返回了题面也无处安放），而不只是靠 prompt 与
    解析两层检查（module-18 §5.5）。
    """

    question_id: int
    reason: str


@dataclass
class PrepOutlineStage:
    """面试提纲的一个阶段。"""

    seq: int
    phase: str
    duration_min: int
    notes: str


@dataclass
class PrepFocusPoint:
    """考察重点：应验证的能力项 + 理由。"""

    dimension: str
    point: str
    reason: str


@dataclass
class PrepQuestionItem:
    """问题预案的一条：建议提问 + 考察意图 + 可追问方向。"""

    question: str
    intent: str
    follow_ups: list[str] = field(default_factory=list)


@dataclass
class InterviewPrepResult:
    """面试前准备助手的三部分产出。

    三个部分用具名 dataclass 而非 dict：它们会**原样序列化进 interview_prep
    的三个 JSON 列**，前端按字段名渲染。用 dict 会失去字段名的编译期约束，
    「follow_ups 写成 followups」这类错误要到前端才炸。
    """

    outline: list[PrepOutlineStage]
    focus_points: list[PrepFocusPoint]
    question_plan: list[PrepQuestionItem]


class AIProvider(ABC):
    """AI 能力抽象基类。

    九个方法覆盖三条业务线：
      · HR 侧：出题 → 逐题评分 → 多维评分 → 汇总报告
      · 候选人侧：补参考答案 / 刷题判分 / 候选人脱敏反馈
      · 简历驱动：按简历匹配题目 / 生成面试前准备提纲

    全部方法**只接收原始值**（str / list[str] / float / 本模块的 dataclass），
    不接收 ORM 对象。
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
        overall_score: float,
        strengths: list[str],
        weaknesses: list[str],
        dimension_scores: list[DimensionScoreResult],
    ) -> CandidateFeedbackResult:
        """由**评分事实**重写出面向候选人的脱敏反馈。

        ⚠️ 这里**刻意不接收报告的综合结论**（PRD §4.9，2026-09-21 修正）。

        报告那句结论里含招聘方的去留判断（「建议进入下一轮 / 不建议继续推进」），
        那是 HR 的决策，该由 HR 另行沟通，不该出现在候选人自助页面上。不把它传进来，
        是**结构上**保证它漏不出去 —— 与 `CandidateFeedbackOut` 用白名单模型保证
        分数不下发是同一手法。若只靠一句「不要复述」的提示约束模型，就退回到
        「把分数发给浏览器再要求它别看」那种靠自觉的做法了。

        因此本方法拿到的是：`dimension_scores`（维度与得分，用于判断强项 / 弱项 ——
        阈值用 `PASS_THRESHOLD`，与 `summarize_report` 同一把尺，不在调用方另算一套）、
        以及报告里那两条**原样**的优缺点列表（**条目与顺序必须保持不变**，
        便于 HR 与候选人逐条对照）。

        level 同时决定返回的 overall_score 是否为 None：
        'summary' → None（默认档，候选人看不到分数）；'full' → 保留原值。
        未知 level 一律按 'summary' 处理 —— 给得更少是安全方向。
        """

    @abstractmethod
    def match_questions_by_resume(
        self,
        resume_text: str,
        position_name: str,
        jd: str,
        dims: list[str],
        candidates: list[QuestionBrief],
        count: int,
    ) -> list[MatchedQuestion]:
        """从 candidates 中挑出与简历最相关的题目，按相关度降序返回至多 count 条。

        **只挑不生成**（PRD §6）：返回的 question_id 恒来自 candidates，
        池外 id 一律丢弃；本方法不产生任何新题。

        ⚠️ `resume_text` 为空时**抛 AIProviderError**：调用方本应先判出「未关联
        简历」并整条路都不调用本方法（PRD §6）。这与 `generate_interview_prep`
        的同名参数行为**相反**，不可混淆。

        `dims` 为空（岗位配置缺失）同样抛错；`candidates` 为空则返回空列表 ——
        「题库里没有可匹配的题」是正常业务状态，由调用方决定要不要报错。
        """

    @abstractmethod
    def generate_interview_prep(
        self,
        position_name: str,
        jd: str,
        dims: list[str],
        candidate_name: str,
        resume_text: str | None,
        questions: list[QuestionBrief],
    ) -> InterviewPrepResult:
        """生成面试提纲 / 考察重点 / 问题预案（PRD §4.11）。

        ⚠️ `resume_text` 为 None 或空时**正常运行**，产出不含简历针对性的内容 ——
        未关联简历也能生成提纲，这与 `match_questions_by_resume` 的行为相反。
        `candidate_name` 为空时用「候选人」兜底，`questions` 为空时问题预案
        全由评估维度生成。

        一次生成即整批返回，**不做流式**（PRD §4.11）。
        """
