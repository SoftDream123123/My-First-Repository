"""resume 模块请求 / 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_TITLE_LENGTH = 100
MAX_NAME_LENGTH = 100
MAX_CONTACT_LENGTH = 200

RESUME_LIST_DEFAULT_LIMIT = 50
RESUME_LIST_MAX_LIMIT = 200


class ResumeCreate(BaseModel):
    """新建简历。

    **请求体不含 `created_by`** —— 归属恒取自 token（计划书 §5.1）。让客户端
    有机会指定归属是最常见的一类越权漏洞，因此字段干脆不存在。

    正文长度上限**刻意不在这里校验**：Pydantic 的 `max_length` 会被 main.py 的
    统一处理器收口成 400，而 PRD §7 要求「正文超长」是 **422**。该校验由
    service 层用业务异常表达（见 `service.ContentTooLongError`）。
    """

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str = Field(min_length=1)
    candidate_name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    candidate_contact: str | None = Field(default=None, max_length=MAX_CONTACT_LENGTH)


class ResumeUpdate(BaseModel):
    """更新简历 —— **部分更新语义**（计划书 §4.2）。

    PRD §8 已把该端点定为 `PUT`，但按「只改传了的字段」实现：前端改个标题
    不该要求把 20000 字正文一起回传。

    可选字段传 `null` 视为「未提供」（不改），传空串表示「清空」—— 想清空
    就填空串，二者在展示上等价，因此不值得引入 `model_fields_set` 区分
    「显式置空」与「缺省」（计划书 §10）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str | None = Field(default=None, min_length=1)
    candidate_name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    candidate_contact: str | None = Field(default=None, max_length=MAX_CONTACT_LENGTH)


class ResumeOut(BaseModel):
    """候选人自己的简历视图。

    列表也下发 `content` 全文：数据量是「简历数 × 一段文本」，不是
    「会话数 × 题目数」，轻量化在这里没有收益，反而让编辑回显多一次请求。
    `created_by` **不下发** —— 候选人无需知道自己的 user id。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    candidate_name: str | None
    candidate_contact: str | None
    created_at: datetime
    updated_at: datetime
