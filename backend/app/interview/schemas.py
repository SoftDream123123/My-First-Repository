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

    password 在「账号已存在且角色为 candidate」时被**忽略** ——
    否则「凭邀请码重置他人密码」会成为一条越权路径。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128, description="最少 8 字符")


# ==================== 候选人侧 ====================


class CandidateInterviewItem(BaseModel):
    """「我参与的面试」列表项。"""

    id: int
    position_name: str
    status: str
    question_count: int
    answered_count: int
    submitted: bool
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
    """面试详情 —— 刻意不含 HR 的评语、评分、其他候选人的作答与 created_by。"""

    id: int
    position_name: str
    status: str
    created_at: datetime
    submitted: bool
    submitted_at: datetime | None
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
