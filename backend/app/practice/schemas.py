"""practice 模块请求 / 响应模型。

关于筛选条件：**复用 `question.schemas.PracticeFilters`**，本模块不另定义一份。
取题的筛选词汇属于 question（它描述「按什么条件从题库取题」），practice 只是
透传。定义第二份同形 dataclass 只会让两者在字段增减时漂移。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MAX_PRACTICE_ANSWER_LENGTH = 5000

DifficultyLiteral = Literal["easy", "medium", "hard"]
QuestionTypeLiteral = Literal["single_choice", "short_answer"]


class PracticeSessionCreate(BaseModel):
    """开始一次练习。全部筛选条件可选 —— 不选即全库随机刷题。"""

    position_id: int | None = None
    category: str | None = Field(default=None, max_length=50)
    dimension: str | None = Field(default=None, max_length=50)
    difficulty: DifficultyLiteral | None = None
    question_type: QuestionTypeLiteral | None = None
    # 上限由配置项 PRACTICE_SESSION_SIZE_MAX 决定，故在 service 层校验而非此处
    size: int | None = Field(default=None, ge=1)
    # 传了就按简历推荐取题；不传则完全走既有筛选逻辑。
    # `ge=1` 在这里拦（纯参数形态问题）；题数上限在 service 拦（上限来自配置项）
    # —— 两者处理方式不同，原因不同，不是不一致。
    resume_id: int | None = Field(default=None, ge=1)


class PracticeItemSubmit(BaseModel):
    """提交某题作答。"""

    item_id: int
    # 允许空串 —— 视为未作答，判 0 分
    user_answer: str = Field(default="", max_length=MAX_PRACTICE_ANSWER_LENGTH)


class PracticeSessionOut(BaseModel):
    id: int
    status: str
    position_id: int | None
    category: str | None
    dimension: str | None
    difficulty: str | None
    question_type: str | None
    total: int
    answered_count: int
    correct_count: int
    started_at: datetime
    finished_at: datetime | None


class PracticeProgress(BaseModel):
    answered_count: int
    correct_count: int
    total: int


class PracticeItemOut(BaseModel):
    """会话详情里的一道待答项。

    `question` 由 item 的**快照**拼装（不是联表读题库当前值），因此题库改题后
    历史练习的复看内容保持不变。

    explanation / reference_answer **只在已提交后才非空** —— 这是「提交后展示」
    规则的落点。不允许用「前端不显示」来替代：不下发就是不下发。
    """

    item_id: int
    seq: int
    question: dict
    user_answer: str | None
    is_correct: bool | None
    score: float | None
    explanation: str | None
    reference_answer: str | None


class PracticeSessionDetail(BaseModel):
    """会话详情。

    两个新字段只出现在**详情**（含创建响应），列表项刻意不加：列表主要在回答
    「我练过哪些」，不是在回答「当时用了哪份简历」，且它要保持轻量。
    """

    session: PracticeSessionOut
    items: list[PracticeItemOut]
    # 本次练习关联的简历；null = 未关联
    resume_id: int | None = None
    # 本次是否**真的**按简历选排了题目。
    # 与 resume_id 不同：AI 失败 / 未命中时会降级为普通筛选，此时
    # resume_id 仍有值（候选人想用的那份）而本字段为 false。
    resume_match_applied: bool = False


class PracticeItemResult(BaseModel):
    """提交某题后返回的判分结果。"""

    item_id: int
    seq: int
    user_answer: str
    # None = 未判分（无参考答案，或 AI 判分失败）—— 与 False（判错）不同
    is_correct: bool | None
    score: float | None
    # 单选题的参考答案放在 correct_answer，简答题放在 reference_answer
    correct_answer: str | None
    reference_answer: str | None
    explanation: str | None
    progress: PracticeProgress


class DimensionAccuracy(BaseModel):
    dimension: str
    answered: int
    correct: int
    accuracy: float | None


class PracticeSessionSummary(BaseModel):
    session_id: int
    status: str
    total: int
    answered_count: int
    correct_count: int
    # 让候选人知道有几题没判出来，而不是误以为答错了
    unscored_count: int
    accuracy: float | None
    by_dimension: list[DimensionAccuracy]


class WrongBookItem(BaseModel):
    """错题本条目 —— 由 practice_item 派生，不单独建表。

    按 question_id 去重：同一道题练错多次只出现一行，并给出 wrong_count。
    逐条罗列会让错题本被同一道题刷屏，失去「该复习哪些题」的作用。
    """

    question_id: int
    content: str
    options: list[str]
    reference_answer: str | None
    explanation: str | None
    my_wrong_answer: str
    wrong_count: int
    last_wrong_at: datetime | None


class PracticeSessionListItem(BaseModel):
    """会话列表项 —— **不含题目明细**。

    明细走 GET /practice/sessions/{id}。让列表带上全部题目会让「看历史」
    这一动作变重（20 个会话 × 20 道题）。
    """

    session_id: int
    status: str
    position_name: str | None
    category: str | None
    dimension: str | None
    difficulty: str | None
    question_type: str | None
    total: int
    answered_count: int
    correct_count: int
    started_at: datetime
    finished_at: datetime | None


class DimensionStats(BaseModel):
    dimension: str
    answered: int
    scored: int
    correct: int
    accuracy: float | None


class TypeStats(BaseModel):
    question_type: str
    answered: int
    scored: int
    correct: int
    accuracy: float | None


class PracticeStats(BaseModel):
    total_answered: int
    scored_count: int
    unscored_count: int
    correct_count: int
    # 正确率的分母是**已判分**数，不是已作答数 —— 未判分的题与候选人水平无关，
    # 放进分母会系统性低估。
    accuracy: float | None
    session_count: int
    by_dimension: list[DimensionStats]
    by_type: list[TypeStats]
