"""FastAPI 依赖：数据库会话、token 解析、当前用户、角色校验。

注意：本模块对 auth.models.User 采用**函数体内延迟导入**，
以保证 core 不反向依赖任何业务模块（保持依赖单向）。
"""

from collections.abc import Callable, Generator
from typing import TYPE_CHECKING

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
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


def require_role(role: str) -> Callable[..., "User"]:
    """依赖工厂：校验当前用户角色。用法：Depends(require_role("admin"))"""

    def _dependency(user: "User" = Depends(get_current_user)) -> "User":
        if user.role != role:
            raise ForbiddenError()
        return user

    return _dependency
