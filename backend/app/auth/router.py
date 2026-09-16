"""auth 模块 HTTP 端点。

router 层只做参数校验、鉴权与响应包装，业务逻辑一律在 service。
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import ROLE_ADMIN, User
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.core.deps import get_current_user, get_db, require_role

router = APIRouter()


# ------------------------------- 认证 -------------------------------


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    tags=["认证"],
    summary="登录，返回 JWT",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    result = service.login(db, payload.username, payload.password)
    return LoginResponse(
        token=result.token, user=UserOut.model_validate(result.user)
    )


@router.get(
    "/auth/me",
    response_model=UserOut,
    tags=["认证"],
    summary="当前登录用户信息",
)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


# ------------------------------ 用户管理 ------------------------------


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["用户管理"],
    summary="创建用户（仅 admin）",
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(ROLE_ADMIN)),
) -> UserOut:
    user = service.create_user(db, payload.username, payload.password, payload.role)
    return UserOut.model_validate(user)


@router.get(
    "/users",
    response_model=list[UserOut],
    tags=["用户管理"],
    summary="用户列表（仅 admin）",
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(ROLE_ADMIN)),
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in service.list_users(db)]


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    tags=["用户管理"],
    summary="改角色 / 启用禁用（仅 admin）",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(ROLE_ADMIN)),
) -> UserOut:
    user = service.update_user(
        db, actor, user_id, role=payload.role, is_active=payload.is_active
    )
    return UserOut.model_validate(user)
