"""auth 模块业务逻辑：登录、用户管理、数据隔离判定。"""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.models import ROLE_ADMIN, User
from app.core.exceptions import (
    BusinessError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.security import create_access_token, hash_password, verify_password

# 用户名或密码错误时的统一文案 —— 用户不存在与密码错误必须返回完全相同的响应，
# 避免攻击者据此枚举出系统中已存在的用户名。
_LOGIN_FAILED_MESSAGE = "用户名或密码错误"


@dataclass
class LoginResult:
    token: str
    user: User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """供 core.deps.get_current_user 使用。"""
    return repository.get_by_id(db, user_id)


def login(db: Session, username: str, password: str) -> LoginResult:
    """校验凭据并签发 JWT。"""
    user = repository.get_by_username(db, username)

    if user is None or not verify_password(password, user.password_hash):
        # 时序加固：用户不存在时也执行一次哈希比对，拉平两条分支的响应时间
        if user is None:
            verify_password(password, hash_password("timing-attack-mitigation"))
        raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)

    if not user.is_active:
        raise UnauthorizedError("账号已禁用，请联系管理员")

    return LoginResult(token=create_access_token(user.id), user=user)


def create_user(db: Session, username: str, password: str, role: str) -> User:
    """创建用户（仅 admin 可达）。"""
    if repository.get_by_username(db, username) is not None:
        raise BusinessError("用户名已存在")

    user = repository.create(db, username, hash_password(password), role)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发场景下由唯一索引兜底，查重只是为了给出友好报错
        db.rollback()
        raise BusinessError("用户名已存在") from exc

    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return repository.list_all(db)


def update_user(
    db: Session,
    actor: User,
    user_id: int,
    role: str | None = None,
    is_active: bool | None = None,
) -> User:
    """修改用户角色 / 启用状态（仅 admin 可达）。"""
    if actor.id == user_id:
        # 防呆：避免管理员把自己降级或禁用，导致系统无人可管
        raise BusinessError("不能修改自己的角色或状态")

    user = repository.get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("用户不存在")

    fields: dict[str, object] = {}
    if role is not None:
        fields["role"] = role
    if is_active is not None:
        fields["is_active"] = is_active

    if fields:
        repository.update(db, user, **fields)
        db.commit()
        db.refresh(user)

    return user


def scope_owner_id(user: User) -> int | None:
    """数据隔离的统一判定入口。

    admin → None（不过滤，可见全部）
    hr    → user.id（各业务模块据此追加 WHERE created_by = :owner_id）
    """
    return None if user.role == ROLE_ADMIN else user.id


def ensure_resource_visible(user: User, created_by: int, label: str) -> None:
    """统一的单条资源可见性校验。

    各业务模块「取回一条记录后判断能否访问」时调用，保证隔离规则只有一处实现。
    不可见时抛 ForbiddenError（403）而非 NotFoundError —— 语义明确：资源存在但无权访问。
    """
    owner_id = scope_owner_id(user)
    if owner_id is not None and created_by != owner_id:
        raise ForbiddenError(f"无权限访问该{label}")
