"""auth 模块请求 / 响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 可**指派**的角色（admin 通过 /users 创建或修改用户时的取值）。
# 刻意不含 candidate —— 候选人账号只能来自自助注册或凭邀请码激活，
# 保证每个候选人账号都与刷题或某场面试有真实关联（PRD §4.1）。
RoleLiteral = Literal["admin", "hr"]

# 系统**存在**的角色（用于文档与类型标注）。
# 注意 UserOut.role 仍是 str：它是既有对外契约，不因新增角色而收紧校验行为。
AnyRoleLiteral = Literal["admin", "hr", "candidate"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """对外的用户视图 —— 刻意不含 password_hash。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128, description="最少 8 字符")
    role: RoleLiteral


class UserUpdate(BaseModel):
    role: RoleLiteral | None = None
    is_active: bool | None = None


class CandidateRegisterRequest(BaseModel):
    """候选人自助注册。

    刻意**不接收 role 字段** —— 落库角色恒为 candidate，请求体无法指定。
    与 QuestionCreate 不接收 source 是同一手法：服务端决定的事实不进请求体。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128, description="最少 8 字符")
