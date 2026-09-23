"""interview 模块请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_ANSWER_LENGTH = 10000


class InterviewCreate(BaseModel):
    position_id: int
    candidate_name: str = Field(min_length=1, max_length=100)
    candidate_contact: str | None = Field(default=None, max_length=200)


class InterviewPatch(BaseModel):
    """只改候选人信息 —— 状态迁移走 /complete、/rollback 等动词端点。"""

    candidate_name: str | None = Field(default=None, min_length=1, max_length=100)
    candidate_contact: str | None = Field(default=None, max_length=200)


class AnswerCreate(BaseModel):
    interview_question_id: int
    # 允许空串，表示「候选人未作答」，评估时按 0 分处理
    content: str = Field(default="", max_length=MAX_ANSWER_LENGTH)


class QuestionItem(BaseModel):
    interview_question_id: int
    seq: int
    content: str
    dimension: str
    source: str
    answer: str | None = None
    recorded_at: datetime | None = None
    # 作答来源（hr / candidate）。
    #
    # 命名为 answer_source 而非 source：本对象已有 source = **题目**来源快照
    # （bank / ai），同名会把两个不同概念混在一起。
    # 该字段只出现在 HR 侧视图 —— 对候选人而言「谁写的」没有意义（只可能是他自己）。
    answer_source: str | None = None
    # AI 给出的简历匹配理由；**仅 HR 侧视图**，非匹配来源的题为 null。
    # 它描述「候选人简历的哪段经历对应这道题」，属于 HR 的评估思路，
    # **绝不下发给候选人**（PRD §4.6）。
    match_reason: str | None = None


class InterviewListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    position_name: str
    candidate_name: str
    candidate_contact: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None
    question_count: int
    answered_count: int


class InterviewDetail(InterviewListItem):
    jd: str
    evaluation_dimensions: list[str]
    questions: list[QuestionItem]
    # 该面试关联的候选人简历 id；null = 尚未关联（前端据此显示「等待候选人提交简历」）
    resume_id: int | None = None


# ==================== 作答邀请（HR 侧）====================


class InvitationView(BaseModel):
    """邀请对象。

    status 有四个取值：pending / accepted / revoked / **expired**。
    最后一个不在数据库里 —— 由 expires_at 读取时派生（见 service）。
    """

    id: int
    interview_id: int
    code: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    candidate_username: str | None
    created_at: datetime


class InvitationAcceptRequest(BaseModel):
    """凭邀请码建号。

    账号已存在且角色为 candidate 时，password 是**身份凭据**：必须与库中密码
    一致才复用该账号，否则「知道对方用户名」就等于能把他人的账号绑到自己的
    邀请上（PRD §4.1）。

    password 可省略（2026-09-23，PRD §4.1 的免密分支）：请求带的有效 JWT 指向的
    账号**就是**这次要绑定的账号时，身份已由此证明，不必再输一次密码。
    这是手机验证码登录能走通邀请链的前提 —— 手机号自动建号的账号没有可用密码。

    ⚠️ 长度约束仅在**提供了密码**时生效（`min_length=8` 对 None 不适用）。
    不能因为字段可省略就把 `min_length` 一并去掉：它保护的是**新建账号**那条
    路径（password 会成为账号的新密码），去掉会允许 3 位密码注册。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description="账号已存在时用它证明身份；新建账号时它就是新密码；"
        "持有该账号的有效 JWT 时可省略",
    )


# ==================== 候选人侧 ====================


class CandidateInterviewItem(BaseModel):
    """「我参与的面试」列表项。

    `resume_id` **必须下发**（PRD §4.13）：候选人端要在「我的简历」页一次列出
    「我每一场用的是哪一份」，缺了它就只能盲勾、也判断不出该不该给「解除」。
    关联状态是他自己的数据 —— **能写就必须能读**。
    """

    id: int
    position_name: str
    status: str
    question_count: int
    answered_count: int
    submitted: bool
    resume_id: int | None = None
    created_at: datetime


class CandidateQuestionItem(BaseModel):
    """候选人在线答题看到的一道题。

    content / dimension 取自**快照**，因此天然不含参考答案
    （content_snapshot 只快照题干）—— 这是既有设计带来的安全收益。
    """

    interview_question_id: int
    seq: int
    content: str
    dimension: str
    my_answer: str | None = None


class CandidateInterviewDetail(BaseModel):
    """面试详情 —— 刻意不含 HR 的评语、评分、其他候选人的作答与 created_by。

    `resume_id` 与列表项同义（PRD §4.13）：候选人要能看出这场关联了哪一份简历。
    它**不是**敏感信息 —— 它指的是候选人自己的简历。
    """

    id: int
    position_name: str
    status: str
    created_at: datetime
    submitted: bool
    submitted_at: datetime | None
    resume_id: int | None = None
    questions: list[CandidateQuestionItem]


class CandidateAnswerCreate(BaseModel):
    """候选人提交作答。

    不接收 source —— 由服务端写入（与 QuestionCreate 不接收 source 同一手法）。
    """

    interview_question_id: int
    # 允许空串，表示「暂不作答」
    content: str = Field(default="", max_length=MAX_ANSWER_LENGTH)


class CandidateAnswerView(BaseModel):
    interview_question_id: int
    content: str
    submitted_at: datetime | None


class InvitationAcceptResult(BaseModel):
    """接受邀请的响应 —— **不含 token**（登录态由 /auth/login 单独获取）。"""

    interview_id: int
    interview: dict


class SubmitResult(BaseModel):
    interview_id: int
    submitted_at: datetime
    answered_count: int


# ==================== 简历关联（HR 只读 / 候选人写入）====================

# 单次补题的题数上限。它是接口卫生，不随产品调整，故写死在 schema 而不是配置
# （默认题数才是产品可调的量，见 RESUME_MATCH_COUNT）。
MATCH_COUNT_MAX = 20


class InterviewResumeOut(BaseModel):
    """HR 看到的候选人简历（只读）。

    `updated_at` 必须下发：HR 据此判断手上这份是不是最新的
    （候选人改了简历后需重新触发补题，PRD §4.13）。
    `created_by` / `created_at` **不下发** —— HR 不需要知道候选人的 user id。
    """

    resume_id: int
    title: str
    content: str
    candidate_name: str | None
    candidate_contact: str | None
    updated_at: datetime


class ResumeLinkRequest(BaseModel):
    """候选人把简历关联到面试（或解除）。

    `resume_id` **必填且可为 null**：与「可选字段」的语义不同，这里
    `null` 是显式的「解除关联」动作。若允许缺省，就无法区分「没传」与
    「要清空」—— 而在本场景**清空是有意义的操作**（PRD §4.13）。
    """

    resume_id: int | None


class MatchRequest(BaseModel):
    """按简历补题的请求体。缺省题数取配置 RESUME_MATCH_COUNT。"""

    count: int | None = Field(default=None, ge=1, le=MATCH_COUNT_MAX)


class MatchAddedItem(BaseModel):
    interview_question_id: int
    seq: int
    content: str
    dimension: str
    match_reason: str | None


class MatchResult(BaseModel):
    """补题结果。

    `added_count == 0` 是**正常结果**（200）：AI 认为候选池里没有更相关的题了。
    `total_questions` 供前端显示「本场共 N 题」—— 补题会累加，不显示总数
    的话 HR 连点几次会以为界面卡了（module-19 §5.3）。
    """

    added_count: int
    added: list[MatchAddedItem]
    total_questions: int


# ==================== 面试前准备助手 ====================


class PrepOutlineStageOut(BaseModel):
    seq: int = Field(ge=1)
    phase: str = Field(min_length=1)
    duration_min: int = Field(ge=1)
    notes: str


class PrepFocusPointOut(BaseModel):
    dimension: str = Field(min_length=1)
    point: str = Field(min_length=1)
    reason: str


class PrepQuestionItemOut(BaseModel):
    question: str = Field(min_length=1)
    intent: str
    follow_ups: list[str]


class PrepOut(BaseModel):
    """查看 / 生成 / 编辑的统一响应。

    `edited_at` 为 null 表示当前内容是 AI 原样产出；非 null 表示 HR 改过。
    """

    interview_id: int
    outline: list[PrepOutlineStageOut]
    focus_points: list[PrepFocusPointOut]
    question_plan: list[PrepQuestionItemOut]
    generated_at: datetime
    edited_at: datetime | None


class PrepUpdate(BaseModel):
    """编辑准备提纲 —— **三部分全部必填**。

    整体替换、不做字段级合并（PRD §5.2）：允许部分提交就需要回答「没提交的
    那部分保留还是清空」，而这个问题的答案依场景而变，语义无法唯一。
    未生成就编辑 → 404（先 POST 生成、再 PUT 编辑是显式且唯一的顺序）。
    """

    outline: list[PrepOutlineStageOut]
    focus_points: list[PrepFocusPointOut]
    question_plan: list[PrepQuestionItemOut]


# ==================== 简历 AI 评估（PRD §4.15）====================


class ResumeReviewView(BaseModel):
    """HR 侧的简历评估视图。

    `match_score` **恒非空** —— HR 看全部评分（§4.9 的既有口径），档位只作用于
    候选人侧。因此与候选人那个 schema **分开写**而不是共用一个可空字段：共用会把
    「HR 也可能拿到 null」写进类型里，让前端对 HR 侧写一段永远不触发的空值分支。
    """

    match_score: float
    conclusion: str
    strengths: list[str]
    gaps: list[str]


class CandidateResumeReviewView(BaseModel):
    """候选人侧的简历评估视图（§4.15、§9）。

    `match_score` 在 `summary` 档为 `null`、`full` 档为 0–10；`conclusion` /
    `strengths` / `gaps` **任何档位都下发** —— 分数是评估结果，文案是可照做的建议。

    字段保留为可空而非「结构上不存在」，与 `generate_candidate_feedback` 的
    `overall_score` 同一形态（PRD §10）。**不下发档位本身**：候选人不需要知道
    部署配了哪一档。
    """

    match_score: float | None
    conclusion: str
    strengths: list[str]
    gaps: list[str]
