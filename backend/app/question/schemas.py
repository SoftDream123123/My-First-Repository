"""question 模块请求 / 响应模型与筛选条件。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TAGS = 10
MAX_TAG_LENGTH = 20

DifficultyLiteral = Literal["easy", "medium", "hard"]
SourceLiteral = Literal["bank", "ai"]
QuestionTypeLiteral = Literal["single_choice", "short_answer"]

MAX_EXPLANATION_LENGTH = 2000


def validate_tags(value: list[str]) -> list[str]:
    """校验并规范化标签：≤10 个、单个 1–20 字符、strip 后去重。"""
    if not isinstance(value, list):
        raise ValueError("标签必须是字符串列表")
    if len(value) > MAX_TAGS:
        raise ValueError(f"标签不能超过 {MAX_TAGS} 个")

    cleaned: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("标签必须是字符串")
        item = raw.strip()
        if not item:
            raise ValueError("标签不能为空")
        if len(item) > MAX_TAG_LENGTH:
            raise ValueError(f"单个标签不能超过 {MAX_TAG_LENGTH} 个字符")
        if item not in cleaned:
            cleaned.append(item)

    return cleaned


class _QuestionBase(BaseModel):
    position_id: int
    category: str | None = Field(default=None, min_length=1, max_length=50)
    dimension: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=5, max_length=2000)
    difficulty: DifficultyLiteral = "medium"
    tags: list[str] = Field(default_factory=list)

    # ---- 刷题相关字段（MVP-2）----
    #
    # 四个字段一律**可缺省**，且缺省值都是 None。原因见 service 的 update_question：
    # 「缺省」与「显式传 null」在更新语义上不同 —— 前者表示不改动，后者表示清空。
    # 若在这里给 question_type 一个 "short_answer" 默认值，客户端改个题干就会把
    # 单选题静默翻成简答题。
    #
    # 选项与参考答案的**跨字段**校验（数量、是否重复、答案是否属于选项）放在
    # service，因为报错文案随题型不同，且与既有的 _assert_dimension_belongs 同一风格。
    question_type: QuestionTypeLiteral | None = None
    options: list[str] | None = None
    reference_answer: str | None = Field(
        default=None, max_length=2000, description="单选题必填且须为选项之一"
    )
    explanation: str | None = Field(default=None, max_length=MAX_EXPLANATION_LENGTH)

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, value: list[str]) -> list[str]:
        return validate_tags(value)


class QuestionCreate(_QuestionBase):
    """source 由服务端决定，客户端不可指定。"""


class QuestionUpdate(_QuestionBase):
    """全量替换语义。

    既有字段（position_id / dimension / content）仍是必填全覆盖；
    四个 MVP-2 新字段缺省时表示「保持不变」—— 见 service.update_question。
    """


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    category: str
    dimension: str
    content: str
    difficulty: str
    question_type: str
    options: list[str]
    reference_answer: str | None
    explanation: str | None
    tags: list[str]
    source: str
    created_by: int
    created_at: datetime


class PracticeQuestionOut(BaseModel):
    """候选人视图 —— **本模块最重要的安全边界**。

    刻意**不含** reference_answer / explanation / source / created_by / created_at：
    参考答案与解析只在**提交作答之后**由 practice 的判分响应返回。若沿用 QuestionOut
    直接下发，候选人一次请求就能拿到全部答案，刷题闭环失去意义。

    用 Pydantic 白名单模型（而非「前端不渲染」）来落地这条规则：未定义的字段
    不可能出现在响应里，可被代码评审、可被测试断言，也不可能被前端疏忽绕过。

    options **必须下发** —— 否则前端的单选框没有内容可渲染。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    category: str
    dimension: str
    difficulty: str
    content: str
    question_type: str
    options: list[str]
    tags: list[str]


class PracticePreviewOut(BaseModel):
    """刷题预览的响应。

    **为什么不是裸数组**：预览要回答两个问题 —— 「一共有多少题可选」与
    「筛选下拉里有哪些分类/维度」。前者必须是**真实题量**，而后者的数据源
    （`items`）为了不一次拉全库是按 `limit` 截断的。两者装在一个对象里，
    调用方就不必再拿被截断的长度去冒充题量。
    """

    total: int
    items: list[PracticeQuestionOut]


class PracticePositionOut(BaseModel):
    """候选人侧的刷题岗位筛选项。

    只有 id / 名称 / 题量：岗位 JD 属 HR 侧内容，候选人端只需一个筛选标识。
    不按 created_by 过滤 —— 口径必须与取题一致（见 service.list_practice_positions）。
    """

    id: int
    name: str
    question_count: int


@dataclass
class QuestionFilters:
    """列表筛选条件，多个条件之间为 AND 关系。"""

    position_id: int | None = None
    category: str | None = None
    dimension: str | None = None
    source: str | None = None
    keyword: str | None = None
    question_type: str | None = None
    difficulty: str | None = None


@dataclass
class PracticeFilters:
    """刷题取题的筛选条件（供 practice 模块透传）。"""

    position_id: int | None = None
    category: str | None = None
    dimension: str | None = None
    difficulty: str | None = None
    question_type: str | None = None
