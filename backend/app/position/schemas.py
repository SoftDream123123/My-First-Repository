"""position 模块请求 / 响应模型，含评估维度校验规则。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DIMENSIONS = 10
MAX_DIMENSION_LENGTH = 50


def validate_dimensions(value: list[str]) -> list[str]:
    """校验并规范化评估维度列表。

    规则（模块计划书 §3.3）：
    - 至少 1 个、至多 10 个
    - 单项 1–50 字符，保存 strip 后的原始大小写
    - strip 后不区分大小写去重
    """
    if not isinstance(value, list):
        raise ValueError("评估维度必须是字符串列表")

    if len(value) > MAX_DIMENSIONS:
        raise ValueError(f"评估维度不能超过 {MAX_DIMENSIONS} 个")

    cleaned: list[str] = []
    seen: set[str] = set()

    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("评估维度必须是字符串")

        item = raw.strip()
        if not item:
            raise ValueError("评估维度不能为空")
        if len(item) > MAX_DIMENSION_LENGTH:
            raise ValueError(
                f"单个评估维度不能超过 {MAX_DIMENSION_LENGTH} 个字符：{item[:20]}…"
            )

        key = item.lower()
        if key in seen:
            raise ValueError(f"评估维度重复：{item}")
        seen.add(key)
        cleaned.append(item)

    if not cleaned:
        raise ValueError("至少需要 1 个评估维度")

    return cleaned


DimensionList = Annotated[list[str], Field(min_length=1)]


class PositionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    jd: str = Field(min_length=1, max_length=10000)
    evaluation_dimensions: DimensionList

    @field_validator("evaluation_dimensions")
    @classmethod
    def _check_dimensions(cls, value: list[str]) -> list[str]:
        return validate_dimensions(value)


class PositionUpdate(BaseModel):
    """全量替换语义。"""

    name: str = Field(min_length=1, max_length=100)
    jd: str = Field(min_length=1, max_length=10000)
    evaluation_dimensions: DimensionList

    @field_validator("evaluation_dimensions")
    @classmethod
    def _check_dimensions(cls, value: list[str]) -> list[str]:
        return validate_dimensions(value)


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    jd: str
    evaluation_dimensions: list[str]
    created_by: int
    created_at: datetime
