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
