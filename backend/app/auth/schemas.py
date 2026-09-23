"""auth 模块请求 / 响应模型。"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 可**指派**的角色（admin 通过 /users 创建或修改用户时的取值）。
# 刻意不含 candidate —— 候选人账号只能来自自助注册或凭邀请码激活，
# 保证每个候选人账号都与刷题或某场面试有真实关联（PRD §4.1）。
RoleLiteral = Literal["admin", "hr"]

# 系统**存在**的角色（用于文档与类型标注）。
# 注意 UserOut.role 仍是 str：它是既有对外契约，不因新增角色而收紧校验行为。
AnyRoleLiteral = Literal["admin", "hr", "candidate"]

# 大陆手机号：1 开头、第二位 3–9、共 11 位（PRD §4.16）。只支持大陆号。
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")

# 归一化时剔除的分隔符。用户从通讯录复制来的号码常带空格与连字符。
_PHONE_SEPARATORS_RE = re.compile(r"[\s\-()]")


def normalize_phone(raw: str) -> str:
    """把手机号归一到 11 位纯数字。

    归一化必须发生在**校验之前**：若允许 `+8613800138000` 与 `13800138000`
    两种写法各自通过校验，`user.phone` 的唯一约束就挡不住「同一个号占两行」——
    而这个号的主人会拿到两个账号（PRD §4.16）。

    前端 `components/phone-login.js` 有一份等价的 JS 实现。两边必须一致：
    不一致的症状是「前端说格式对、后端说格式错」，一条谁也想不到去查前端的错误。

    只剥**一层**国家码前缀：`"868613800138000"` 这种叠了两层的脏数据
    应当判为非法，而不是被反复剥成一个合法号码。
    """
    cleaned = _PHONE_SEPARATORS_RE.sub("", raw or "")
    for prefix in ("+86", "86"):
        # 长度必须严格大于前缀，否则 `"86"` 会被剥成空串
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned


def _clean_phone_field(value: object) -> object:
    """字段校验器共用实现。None 原样放行（`UserUpdate` 用它表达「解绑」）。"""
    if value is None:
        return None
    if not isinstance(value, str):
        return value  # 交给 pydantic 报类型错，文案比这里自己编的更准
    cleaned = normalize_phone(value)
    if not _PHONE_RE.match(cleaned):
        raise ValueError("请填写 11 位大陆手机号")
    return cleaned


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class PhoneCodeRequest(BaseModel):
    """发码请求（PRD §4.16）。"""

    phone: str = Field(max_length=30)

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        return _clean_phone_field(value)


class PhoneCodeResponse(BaseModel):
    """发码响应。

    结构**不区分手机号是否已注册** —— 否则这个端点就成了一个手机号枚举接口
    （PRD §4.16）。`dev_code` 仅在 `SMS_PROVIDER=mock` 时非空。
    """

    expires_in: int
    dev_code: str | None = None


class PhoneLoginRequest(BaseModel):
    """验证码登录请求（PRD §4.16）。"""

    phone: str = Field(max_length=30)
    code: str = Field(min_length=1, max_length=10)

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        return _clean_phone_field(value)


class UserOut(BaseModel):
    """对外的用户视图 —— 刻意不含 password_hash。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    # 手机号下发是安全的：本视图只出现在 /auth/me（本人）、/auth/login 与
    # /auth/phone/login 的响应（本人）、以及 /users（仅 admin）里，
    # 没有任何一条会把它发给「别人」。
    phone: str | None = None
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
    # 绑定 / 解绑手机号（PRD §4.1、§4.16）。
    #
    # ⚠️ 「不传」与「传 null」语义不同：不传 = 不改，传 null = 解绑。
    # 既有两个字段用 `if role is not None` 判定，**区分不了**这两者 ——
    # 对它们无害（没有「清空角色」的需求），但手机号需要一个解除绑定的入口。
    # 因此 router / service 改用 `payload.model_fields_set`：
    # `"phone" in payload.model_fields_set` 表示调用方确实传了这个键（哪怕值是 null）。
    phone: str | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        return _clean_phone_field(value)


class CandidateRegisterRequest(BaseModel):
    """候选人自助注册。

    刻意**不接收 role 字段** —— 落库角色恒为 candidate，请求体无法指定。
    与 QuestionCreate 不接收 source 是同一手法：服务端决定的事实不进请求体。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128, description="最少 8 字符")
