"""evaluation 模块请求 / 响应模型与 SSE 事件结构。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


@dataclass
class EvaluationEvent:
    """SSE 事件。

    name 取值：question | dimension | report | done | error
    """

    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EvaluateTriggerResponse(BaseModel):
    interview_id: int
    status: str
    stream_url: str


class DimensionScoreItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension: str
    score: float
    comment: str


class QuestionScoreItem(BaseModel):
    interview_question_id: int
    seq: int
    content: str
    dimension: str
    answer: str | None
    score: float
    comment: str


class ReportDetail(BaseModel):
    """完整报告：逐题 + 多维 + 汇总（PRD §4.5 的四项输出 + 明细）。"""

    interview_id: int
    candidate_name: str
    position_name: str
    overall_score: float
    conclusion: str
    strengths: list[str]
    weaknesses: list[str]
    evaluated_at: datetime
    dimension_scores: list[DimensionScoreItem]
    question_scores: list[QuestionScoreItem]
