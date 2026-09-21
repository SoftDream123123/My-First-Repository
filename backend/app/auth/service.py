"""auth 模块业务逻辑：登录、用户管理、数据隔离判定。"""

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.models import ROLE_ADMIN, ROLE_CANDIDATE, ROLE_HR, User
from app.core.config import get_settings
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

    其他角色（含 candidate）→ 抛 ForbiddenError。

    这是**纵深防御**：候选人不是 HR 数据的可见者，而 HR 侧路由的角色守卫
    本应在此之前就拦下他们。此处的拒绝不依赖守卫是否挂全 —— 任何漏挂守卫的
    新端点，都会在这里被拦住。两种错误做法都比抛错更糟：
      · 返回 None         → 等于不过滤，候选人看到全部数据（最坏的失败方向）
      · 返回 user.id      → 把候选人当作「创建者」，语义上伪造了一个事实
    """
    if user.role == ROLE_ADMIN:
        return None
    if user.role == ROLE_HR:
        return user.id
    raise ForbiddenError()


def ensure_resource_visible(user: User, created_by: int, label: str) -> None:
    """统一的单条资源可见性校验。

    各业务模块「取回一条记录后判断能否访问」时调用，保证隔离规则只有一处实现。
    不可见时抛 ForbiddenError（403）而非 NotFoundError —— 语义明确：资源存在但无权访问。
    """
    owner_id = scope_owner_id(user)
    if owner_id is not None and created_by != owner_id:
        raise ForbiddenError(f"无权限访问该{label}")


def ensure_owner_match(user: User, owner_id: int, label: str) -> None:
    """通用的资源归属校验：这条记录是不是我的。

    与 `ensure_resource_visible` 的分工必须分清：
      · `scope_owner_id` / `ensure_resource_visible` 回答「HR 能看到哪些」
        —— 判据是 `created_by`，且对 candidate 角色直接抛错。
      · `ensure_owner_match` 回答「这条记录是不是我的」—— 适合
        `practice_session.candidate_user_id` 这类**非 HR 拥有**的资源。

    候选人必须走本函数：用 `ensure_resource_visible` 会让候选人连自己的
    练习都读不到（见 module-16 §4 的纵深防御）。
    """
    if user.role == ROLE_ADMIN:
        return
    if user.id != owner_id:
        raise ForbiddenError(f"无权限访问该{label}")


def register_candidate(db: Session, username: str, password: str) -> User:
    """候选人自助注册（公开端点，PRD §4.1）。

    只创建 candidate 角色账号。用户名命名空间与 admin/hr 共享，
    因此「已被占用」不区分占用者角色 —— 区分等于提供了一个账号角色探测接口。
    """
    if not get_settings().candidate_self_register:
        raise BusinessError(
            "候选人自助注册已关闭，请使用邀请码激活",
            detail={"reason": "self_register_disabled"},
        )

    return _create_candidate(db, username, password)


def create_candidate_account(db: Session, username: str, password: str) -> User:
    """凭邀请码创建 / 复用候选人账号（供 interview 模块调用）。

    与自助注册的区别：**不校验 CANDIDATE_SELF_REGISTER 开关**。
    该开关控制的是「开放注册」，不是「凭邀请建号」—— 关闭自助注册后，
    邀请码仍是候选人的唯一入口，必须可用。

    已存在同名 candidate 时**校验密码后复用**该账号（候选人可能已注册了刷题账号，
    不应被迫换用户名）。**密码不符即拒绝**，见函数体里的说明。

    已存在同名 hr/admin 时**硬拒绝** —— 否则 HR 账号会被
    写进 interview_invitation.candidate_user_id，从而获得候选人才有的
    「查看脱敏反馈」通道，且身份语义自相矛盾。这是越权入口。
    """
    existing = repository.get_by_username(db, username)
    if existing is not None:
        if existing.role == ROLE_CANDIDATE:
            # 复用已有账号**必须比对密码**（PRD §4.1/§7、module-09 §5.2）。
            #
            # 少了这一步，「知道对方用户名」就等于能把自己的邀请码绑到对方账号上，
            # 进而读到对方的面试 —— 比它原先要防的「凭码重置他人密码」更严重。
            # 账号已存在时这个 password 是**身份凭据**而非新密码，因此只比对、不写库。
            #
            # 文案复用登录失败的那一句：不新增可区分的信号。残余的「该用户名是否
            # 存在」可探测性只对**持有有效邀请码**的人成立，而邀请码一次性、高熵、私发。
            if not verify_password(password, existing.password_hash):
                raise UnauthorizedError(_LOGIN_FAILED_MESSAGE)
            return existing
        raise BusinessError("用户名已被占用")

    return _create_candidate(db, username, password)


def _create_candidate(db: Session, username: str, password: str) -> User:
    """创建 candidate 账号（两个入口共用的落库部分）。"""
    if repository.get_by_username(db, username) is not None:
        raise BusinessError("用户名已被占用")

    user = repository.create(db, username, hash_password(password), ROLE_CANDIDATE)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发场景下由唯一索引兜底；查重只是为了给出友好报错
        db.rollback()
        raise BusinessError("用户名已被占用") from exc

    db.refresh(user)
    return user
