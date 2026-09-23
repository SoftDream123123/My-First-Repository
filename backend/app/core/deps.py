"""FastAPI 依赖：数据库会话、token 解析、当前用户、角色校验。

注意：本模块对 auth.models.User 采用**函数体内延迟导入**，
以保证 core 不反向依赖任何业务模块（保持依赖单向）。
"""

from collections.abc import Callable, Generator
from typing import TYPE_CHECKING

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError
from app.core.security import decode_token

if TYPE_CHECKING:  # 仅用于类型标注，运行时不导入
    from app.auth.models import User


def get_token(authorization: str | None = Header(default=None)) -> str:
    """从 `Authorization: Bearer <token>` 中解析出 token。"""
    if not authorization:
        raise UnauthorizedError()

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise UnauthorizedError()

    return parts[1]


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(get_token),
) -> "User":
    """解析 token 并返回当前登录用户。

    用户不存在或已被禁用 → 401。
    返回的 User 是各业务模块做数据隔离的唯一依据。
    """
    # 延迟导入：保持 core 不依赖业务模块
    from app.auth import service as auth_service

    user_id = decode_token(token)
    user = auth_service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError()

    return user


def require_roles(*roles: str) -> Callable[..., "User"]:
    """依赖工厂：校验当前用户角色在允许集内。

    用法：Depends(require_roles("admin", "hr"))

    精确匹配，**不做层级包含** —— 不存在「admin 包含 hr」这类隐式规则。
    HR 侧路由必须显式写出两个角色，候选人是终端用户角色、admin 在其中不通行。
    显式列出是最容易评审的形式：新增角色时不会有意外的放行。
    """
    allowed = frozenset(roles)

    def _dependency(user: "User" = Depends(get_current_user)) -> "User":
        if user.role not in allowed:
            raise ForbiddenError()
        return user

    return _dependency


def require_role(role: str) -> Callable[..., "User"]:
    """单角色守卫，`require_roles` 的薄封装。

    保留它是为了不改动既有调用点（auth.router 的三处 admin 守卫）。
    新代码一律用 `require_roles`。
    """
    return require_roles(role)


def get_optional_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> "User | None":
    """尽力解析当前用户；**任何一步失败都返回 None，绝不抛错**。

    专供**公开端点**做「可选加速」，目前只有一处调用者：候选人激活端点
    `POST /candidate/invitations/{code}/accept` 的免密分支（PRD §4.1）——
    已持有该账号的有效 JWT 时不必再输一次密码。

    ⚠️ 语义与 `get_current_user` **刻意相反**：这里 token 无效**不是**错误，
    只是「没有加速可用」。调用方随后会退回原有的密码校验路径，
    **权限不会被放宽**（判据还要求 token 指向的就是目标账号）。

    若这里改成像 `get_current_user` 那样抛 401，「带着过期 token 去激活」会从
    「按密码正常激活」退化成「激活失败」—— 一个纯粹的功能退化，且症状
    （输了正确密码却进不去）与原因（拦截器把坏 token 当成了错误）离得很远。

    账号**已禁用**时同样返回 None：效果是「禁用账号持 token 时不走免密」，
    随后仍会被 `create_candidate_account` 里的 is_active 检查拦住，不构成绕过。
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None

    # 延迟导入：保持 core 不依赖业务模块
    from app.auth import service as auth_service

    try:
        user_id = decode_token(parts[1])
    except AppError:
        # decode_token 把过期 / 签名错 / 格式错 / sub 非法统一收口成
        # InvalidTokenError（AppError 子类），因此这里一个 except 就够。
        return None

    user = auth_service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None

    return user
