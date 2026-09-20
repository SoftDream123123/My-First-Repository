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


class CandidateFeedbackOut(BaseModel):
    """面向候选人的脱敏反馈 —— **本模块最重要的安全设计**。

    这是一个**白名单**模型：未在此定义的字段不可能出现在响应里。因此
    「候选人看不到逐题分 / 维度分 / 雷达图」这条规则落在**序列化结构**上，
    可被代码评审、可被测试断言，也不可能被前端疏忽绕过。

    靠「前端不渲染」实现脱敏等于把分数发给浏览器再要求它别看 ——
    一个开发者工具就能看到。同理，`PracticeQuestionOut` 剥离参考答案
    （module-10）用的是同一手法。

    客户端**不能指定档位**：档位只来自服务端配置。否则候选人传一个
    `?level=full` 就能拿到自己的总分。
    """

    interview_id: int
    level: str
    conclusion: str
    strengths: list[str]
    weaknesses: list[str]
    # summary 档为 None；full 档为 0–10 的总分。任何档位下都不含明细
    overall_score: float | None
    generated_at: datetime
