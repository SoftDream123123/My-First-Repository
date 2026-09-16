"""question 模块请求 / 响应模型与筛选条件。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TAGS = 10
MAX_TAG_LENGTH = 20

DifficultyLiteral = Literal["easy", "medium", "hard"]
SourceLiteral = Literal["bank", "ai"]


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

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, value: list[str]) -> list[str]:
        return validate_tags(value)


class QuestionCreate(_QuestionBase):
    """source 由服务端决定，客户端不可指定。"""


class QuestionUpdate(_QuestionBase):
    """全量替换语义。"""


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position_id: int
    category: str
    dimension: str
    content: str
    difficulty: str
    tags: list[str]
    source: str
    created_by: int
    created_at: datetime


@dataclass
class QuestionFilters:
    """列表筛选条件，多个条件之间为 AND 关系。"""

    position_id: int | None = None
    category: str | None = None
    dimension: str | None = None
    source: str | None = None
    keyword: str | None = None
