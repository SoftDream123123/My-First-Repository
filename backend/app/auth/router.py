"""auth 模块 HTTP 端点。

router 层只做参数校验、鉴权与响应包装，业务逻辑一律在 service。
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import ROLE_ADMIN, User
from app.auth.schemas import (
    CandidateRegisterRequest,
    LoginRequest,
    LoginResponse,
    PhoneCodeRequest,
    PhoneCodeResponse,
    PhoneLoginRequest,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.core.deps import get_current_user, get_db, require_roles

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


@router.post(
    "/auth/phone/code",
    response_model=PhoneCodeResponse,
    tags=["认证"],
    summary="发送手机验证码（三层限流）",
)
def send_phone_code(
    payload: PhoneCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PhoneCodeResponse:
    """公开端点（PRD §4.16）。

    **响应刻意不区分手机号是否已注册** —— 一律返回同一结构，否则这个端点就是
    一个手机号枚举接口：攻击者能借它判断某个号码是不是本系统用户。

    `dev_code` 仅在 `SMS_PROVIDER=mock` 时非空。它出现与否**完全由后端的
    Provider 决定**，前端只是把它显示出来（module-32 §3.3）。

    `request.client` 可能为 None（ASGI 传输层不给对端信息），此时 IP 维度的限流
    自动跳过 —— 拿不到这个信息不该让用户完全无法发码。单机部署下它就是
    `127.0.0.1`；若将来放到反向代理后面，需改用可信的 `X-Forwarded-For`，
    否则所有请求会共用同一个 IP 配额。
    """
    request_ip = request.client.host if request.client else None
    result = service.send_phone_code(db, payload.phone, request_ip)
    return PhoneCodeResponse(expires_in=result.expires_in, dev_code=result.dev_code)


@router.post(
    "/auth/phone/login",
    response_model=LoginResponse,
    tags=["认证"],
    summary="手机验证码登录，返回 JWT",
)
def login_by_phone(
    payload: PhoneLoginRequest, db: Session = Depends(get_db)
) -> LoginResponse:
    """公开端点（PRD §4.16）。

    ⚠️ **响应体与 `/auth/login` 逐字段一致**（同一个 `LoginResponse`）。这是有意的：
    前端按 `user.role` 分流到 HR 端或候选人端的逻辑因此不需要第二套实现。
    `test_api_auth.py` 有一条用例断言两者的响应键集合完全相等 ——
    给手机登录另加字段会让那条断言失败，而失败是对的。

    手机号未绑定任何账号时**自动创建 candidate 账号**（角色恒为 candidate，
    不可配置，见 `service._create_phone_candidate`）。
    """
    result = service.login_by_phone(db, payload.phone, payload.code)
    return LoginResponse(
        token=result.token, user=UserOut.model_validate(result.user)
    )


@router.post(
    "/auth/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["认证"],
    summary="候选人自助注册（仅刷题权限）",
)
def register_candidate(
    payload: CandidateRegisterRequest, db: Session = Depends(get_db)
) -> UserOut:
    """公开端点（PRD §4.1）。

    刻意**不返回 token**：注册与登录是两个动作，否则 JWT 签发会有两条路径
    （login 与 register），有效期与载荷逻辑出现第二处实现。前端在注册成功后
    自动调 `/auth/login`，用户无感知。
    """
    user = service.register_candidate(db, payload.username, payload.password)
    return UserOut.model_validate(user)


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
    _: User = Depends(require_roles(ROLE_ADMIN)),
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
    _: User = Depends(require_roles(ROLE_ADMIN)),
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in service.list_users(db)]


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    tags=["用户管理"],
    summary="改角色 / 启用禁用 / 绑定解绑手机号（仅 admin）",
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(ROLE_ADMIN)),
) -> UserOut:
    """⚠️ 手机号用 `model_fields_set` 判定，不能判 `is not None`（PRD §4.1）。

    「没传 phone」= 不改，「传 phone: null」= 解绑 —— `None` 本身就是一个有意义的
    取值（解绑），因此不能兼任「没传」这个含义。`role` / `is_active` 用
    `is not None` 是安全的，因为它们没有「清空」的需求；手机号有。
    """
    phone = payload.phone if "phone" in payload.model_fields_set else service.UNSET

    user = service.update_user(
        db,
        actor,
        user_id,
        role=payload.role,
        is_active=payload.is_active,
        phone=phone,
    )
    return UserOut.model_validate(user)
