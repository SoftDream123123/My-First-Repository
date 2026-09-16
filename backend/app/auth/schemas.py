"""auth 模块请求 / 响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoleLiteral = Literal["admin", "hr"]


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
