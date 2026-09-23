"""API 接口测试 —— 模块 2/9/31：auth（登录 / 自助注册 / 当前用户 / 用户管理 / 手机验证码）。

覆盖 8 个 method-route：
    POST   /api/auth/login
    POST   /api/auth/phone/code
    POST   /api/auth/phone/login
    POST   /api/auth/register
    GET    /api/auth/me
    POST   /api/users
    GET    /api/users
    PATCH  /api/users/{user_id}

契约来源：
    docs/superpowers/specs/2026-09-15-module-01-auth-plan.md
    docs/superpowers/specs/2026-09-20-module-09-auth-plan.md  §4.1 / §4.2 / §4.5
    docs/superpowers/specs/2026-09-23-module-31-auth-phone-otp-plan.md  §8
    docs/apis/API接口文档.md §5.1–§5.6

本文件补齐了几处此前没有 HTTP 层用例的边界：`PATCH /users` 的非法 role 与空请求体、
`POST /users` 的用户名超长、登录/注册夹带未知字段。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import create_access_token


# ===========================================================================
# 5.1 登录
# ===========================================================================


def test_login_returns_token_and_user_without_password_hash(client, hr_user):
    resp = client.post(
        "/api/auth/login", json={"username": "hr_test", "password": "hr12345678"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"token", "user"}
    assert body["user"]["username"] == "hr_test"
    assert body["user"]["role"] == "hr"
    assert "password_hash" not in resp.text

    # 拿到的 token 必须真的能用
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


def test_candidate_can_log_in_with_the_same_endpoint(client, candidate_user):
    """三种角色共用同一个登录接口 —— 前端只能靠响应里的 role 分流。"""
    resp = client.post(
        "/api/auth/login", json={"username": "cand_test", "password": "cand12345678"}
    )

    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "candidate"


def test_login_unknown_user_and_wrong_password_are_indistinguishable(client, hr_user):
    """防用户名枚举：两种失败的响应**逐字节相同**。

    若哪天有人给「用户不存在」单独加一句更友好的文案，这条会立刻红 ——
    那条文案同时也是一个枚举接口。
    """
    unknown = client.post(
        "/api/auth/login", json={"username": "no_such_user", "password": "whatever12345"}
    )
    wrong = client.post(
        "/api/auth/login", json={"username": "hr_test", "password": "wrong_password"}
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["code"] == wrong.json()["code"] == "UNAUTHORIZED"
    assert unknown.json()["message"] == wrong.json()["message"]
    assert unknown.text == wrong.text


def test_login_disabled_account_is_rejected(client, db, hr_user, admin_user):
    """账号被禁用后**即使密码正确**也拒绝，且文案与密码错误不同。"""
    from app.auth import service

    service.update_user(db, admin_user, hr_user.id, is_active=False)

    resp = client.post(
        "/api/auth/login", json={"username": "hr_test", "password": "hr12345678"}
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "UNAUTHORIZED"
    assert "禁用" in body["message"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": "only_username"},
        {"password": "only_password"},
        {"username": "", "password": ""},
    ],
)
def test_login_validation_failures_are_400(client, payload):
    resp = client.post("/api/auth/login", json=payload)

    assert resp.status_code == 400, f"{payload} -> {resp.status_code}"
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_login_ignores_unknown_extra_fields(client, hr_user):
    """夹带未知字段不报错（Pydantic 默认忽略）—— 前端多传字段不该炸。"""
    resp = client.post(
        "/api/auth/login",
        json={"username": "hr_test", "password": "hr12345678", "role": "admin", "extra": 1},
    )

    assert resp.status_code == 200
    # 关键：夹带的 role 不能影响真实角色
    assert resp.json()["user"]["role"] == "hr"


# ===========================================================================
# 5.2 当前登录用户
# ===========================================================================


def test_me_returns_current_user(client, candidate_headers, candidate_user):
    resp = client.get("/api/auth/me", headers=candidate_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == candidate_user.id
    assert body["role"] == "candidate"
    # 白名单断言（精确相等，不是"包含"）—— 防的是**多**下发字段，
    # 所以新增字段必须来这里显式登记，否则这条会挂。
    #
    # `phone`（MVP-5）是**本人自己的**手机号，/auth/me 只有本人可达，
    # 因此下发它不构成泄露。/auth/me 从不返回别人的 UserOut。
    assert set(body) == {"id", "username", "phone", "role", "is_active", "created_at"}
    assert body["phone"] is None  # 该夹具是用户名注册的，未绑手机号


def test_role_change_takes_effect_on_an_existing_token(client, db, admin_user):
    """**角色不缓存在 JWT 里** —— 改角色后旧 token 立刻拿到新角色。

    这条直接决定前端能不能缓存 `user.role`：不能。
    """
    from app.auth import service

    user = service.create_user(db, "promote_me", "promote12345", "hr")
    old_token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {old_token}"}

    assert client.get("/api/auth/me", headers=headers).json()["role"] == "hr"

    service.update_user(db, admin_user, user.id, role="admin")

    assert client.get("/api/auth/me", headers=headers).json()["role"] == "admin"


def test_disable_takes_effect_on_an_existing_token(
    client, db, hr_headers, hr_user, admin_user
):
    """禁用后旧 token 立即失效（每次请求都回查 is_active）。"""
    from app.auth import service

    assert client.get("/api/auth/me", headers=hr_headers).status_code == 200

    service.update_user(db, admin_user, hr_user.id, is_active=False)

    resp = client.get("/api/auth/me", headers=hr_headers)
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


def test_me_rejects_non_bearer_scheme(client, hr_user):
    """`Authorization: <token>`（缺 Bearer）→ 401，不静默当匿名处理。"""
    token = create_access_token(hr_user.id)

    resp = client.get("/api/auth/me", headers={"Authorization": token})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


# ===========================================================================
# 5.6 候选人自助注册
# ===========================================================================


def test_register_creates_candidate_without_token(client):
    resp = client.post(
        "/api/auth/register", json={"username": "new_cand", "password": "cand12345678"}
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "candidate"
    assert body["is_active"] is True
    # 注册不等于登录
    assert "token" not in body
    assert "password_hash" not in resp.text


def test_register_result_can_log_in(client):
    client.post(
        "/api/auth/register", json={"username": "login_after_reg", "password": "cand12345678"}
    )

    resp = client.post(
        "/api/auth/login", json={"username": "login_after_reg", "password": "cand12345678"}
    )

    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "candidate"


def test_register_cannot_escalate_to_hr_or_admin(client):
    """请求体里夹带 `role` 无效 —— 自助注册不能成为提权路径。"""
    resp = client.post(
        "/api/auth/register",
        json={"username": "want_admin", "password": "cand12345678", "role": "admin"},
    )

    assert resp.status_code == 201
    assert resp.json()["role"] == "candidate"


def test_register_duplicate_username_of_candidate_is_conflict(client, candidate_user):
    resp = client.post(
        "/api/auth/register", json={"username": "cand_test", "password": "cand12345678"}
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert "占用" in resp.json()["message"]


def test_register_duplicate_username_of_hr_is_indistinguishable_from_candidate(
    client, candidate_user, hr_user
):
    """被占用的名字是 HR 还是候选人，**响应完全一样** —— 否则注册接口就成了
    「该用户名是否存在于 HR 侧」的探测器。"""
    taken_by_candidate = client.post(
        "/api/auth/register", json={"username": "cand_test", "password": "cand12345678"}
    )
    taken_by_hr = client.post(
        "/api/auth/register", json={"username": "hr_test", "password": "cand12345678"}
    )

    assert taken_by_candidate.status_code == taken_by_hr.status_code == 409
    assert taken_by_candidate.json()["message"] == taken_by_hr.json()["message"]


def test_register_short_password_is_400_with_field_detail(client):
    resp = client.post(
        "/api/auth/register", json={"username": "short_pwd", "password": "short"}
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert {f["field"] for f in body["detail"]["fields"]} == {"password"}


def test_register_rejects_username_over_50_chars(client):
    resp = client.post(
        "/api/auth/register", json={"username": "u" * 51, "password": "cand12345678"}
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_register_blocked_when_self_register_disabled(client, monkeypatch):
    """配置关闭 → 409，且带结构化 `detail.reason` 供前端引导到「输入邀请码」。"""
    monkeypatch.setenv("CANDIDATE_SELF_REGISTER", "false")
    get_settings.cache_clear()
    try:
        resp = client.post(
            "/api/auth/register", json={"username": "closed", "password": "cand12345678"}
        )

        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "BUSINESS_ERROR"
        assert body["detail"]["reason"] == "self_register_disabled"
    finally:
        get_settings.cache_clear()


# ===========================================================================
# 5.3 / 5.4 / 5.5 用户管理（仅 admin）
# ===========================================================================


def test_create_user_as_admin_returns_201(client, admin_headers):
    resp = client.post(
        "/api/users",
        json={"username": "hr_new", "password": "hr12345678", "role": "hr"},
        headers=admin_headers,
    )

    assert resp.status_code == 201
    assert resp.json()["role"] == "hr"
    assert "password_hash" not in resp.text


def test_create_user_as_hr_is_forbidden(client, hr_headers):
    resp = client.post(
        "/api/users",
        json={"username": "hr_new", "password": "hr12345678", "role": "hr"},
        headers=hr_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_create_user_cannot_assign_candidate_role(client, admin_headers):
    """`candidate` 不在 `POST /users` 的 role 枚举里 —— 候选人账号只能靠自己注册
    或凭邀请码激活，不能由 admin 直接造。"""
    resp = client.post(
        "/api/users",
        json={"username": "made_candidate", "password": "hr12345678", "role": "candidate"},
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_create_user_rejects_short_password_and_overlong_username(client, admin_headers):
    short = client.post(
        "/api/users",
        json={"username": "hr_x", "password": "short", "role": "hr"},
        headers=admin_headers,
    )
    long_name = client.post(
        "/api/users",
        json={"username": "u" * 51, "password": "hr12345678", "role": "hr"},
        headers=admin_headers,
    )

    assert short.status_code == 400, short.text
    assert long_name.status_code == 400, long_name.text


def test_list_users_as_admin_excludes_password_hash(client, admin_headers, hr_user):
    resp = client.get("/api/users", headers=admin_headers)

    assert resp.status_code == 200
    users = resp.json()
    assert isinstance(users, list) and len(users) >= 2
    assert [u["id"] for u in users] == sorted(u["id"] for u in users), "按 id 升序"
    assert "password_hash" not in resp.text


def test_list_users_as_candidate_is_forbidden(client, candidate_headers):
    resp = client.get("/api/users", headers=candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_patch_user_role_and_disable(client, admin_headers, db):
    from app.auth import service

    target = service.create_user(db, "patch_target", "patch12345", "hr")

    promoted = client.patch(
        f"/api/users/{target.id}", json={"role": "admin"}, headers=admin_headers
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    disabled = client.patch(
        f"/api/users/{target.id}", json={"is_active": False}, headers=admin_headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False


def test_patch_user_with_empty_body_is_a_noop(client, admin_headers, db):
    """⚠️ 补空白：空请求体此前没有用例。

    两个字段都是可选的，所以 `{}` 是**合法**请求 —— 应当是「什么都不改」的 200，
    而不是 400。前端「只提交改动字段」的写法依赖这一点。
    """
    from app.auth import service

    target = service.create_user(db, "noop_target", "noop12345", "hr")

    resp = client.patch(f"/api/users/{target.id}", json={}, headers=admin_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "hr"
    assert body["is_active"] is True


def test_patch_user_with_invalid_role_is_400(client, admin_headers, db):
    """⚠️ 补空白：非法 role 此前只在创建接口测过，PATCH 侧没测。"""
    from app.auth import service

    target = service.create_user(db, "bad_role_target", "bad12345", "hr")

    resp = client.patch(
        f"/api/users/{target.id}", json={"role": "superuser"}, headers=admin_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_patch_user_cannot_assign_candidate_role(client, admin_headers, db):
    from app.auth import service

    target = service.create_user(db, "cand_role_target", "cand12345", "hr")

    resp = client.patch(
        f"/api/users/{target.id}", json={"role": "candidate"}, headers=admin_headers
    )

    assert resp.status_code == 400


def test_patch_self_is_conflict(client, admin_headers, admin_user):
    """防自锁死：admin 不能改自己的角色或状态。"""
    resp = client.patch(
        f"/api/users/{admin_user.id}", json={"role": "hr"}, headers=admin_headers
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"

    disable = client.patch(
        f"/api/users/{admin_user.id}", json={"is_active": False}, headers=admin_headers
    )
    assert disable.status_code == 409


def test_patch_nonexistent_user_is_404(client, admin_headers):
    resp = client.patch("/api/users/424242", json={"role": "hr"}, headers=admin_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_patch_user_as_hr_is_forbidden(client, hr_headers, other_hr):
    resp = client.patch(
        f"/api/users/{other_hr.id}", json={"role": "admin"}, headers=hr_headers
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


# ===========================================================================
# 5.7 发送手机验证码（MVP-5）
# ===========================================================================

PHONE = "13800138000"


def _age_codes(db, phone: str, seconds: int = 120) -> None:
    """把该号已有验证码的发码时间往前推，绕开 60 秒重发间隔。

    不能用「作废」代替：重发间隔看的是 `get_latest_code`，它不论码是否已消费 ——
    它回答的是「上次发码是什么时候」，作废一个码不等于「没发过」。
    """
    db.execute(
        text("UPDATE phone_verification_code SET created_at = :t WHERE phone = :p"),
        {
            "t": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds),
            "p": phone,
        },
    )
    db.commit()


def _send_code(client, phone: str = PHONE):
    return client.post("/api/auth/phone/code", json={"phone": phone})


def _phone_login(client, phone: str, code: str):
    return client.post("/api/auth/phone/login", json={"phone": phone, "code": code})


def test_send_code_returns_ttl_and_dev_code(client):
    resp = _send_code(client)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"expires_in", "dev_code"}
    assert body["expires_in"] == 300
    assert len(body["dev_code"]) == 6 and body["dev_code"].isdigit()


def test_send_code_missing_phone_is_400(client):
    resp = client.post("/api/auth/phone/code", json={})

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "bad",
    ["", "1380013800", "138001380000", "12800138000", "abcdefghijk", "138 0013 8000x"],
)
def test_send_code_invalid_phone_is_400(client, bad):
    """格式非法 → **400**（项目把 Pydantic 校验统一收口为 400，不是 422）。"""
    resp = _send_code(client, bad)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_send_code_rate_limited_is_429(client):
    assert _send_code(client).status_code == 200

    resp = _send_code(client)

    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "TOO_MANY_REQUESTS"
    assert 1 <= body["detail"]["retry_after_seconds"] <= 60


# ===========================================================================
# 5.8 手机验证码登录（MVP-5）
# ===========================================================================


def test_phone_login_unknown_phone_creates_candidate(client):
    code = _send_code(client).json()["dev_code"]

    resp = _phone_login(client, PHONE, code)

    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["role"] == "candidate"
    assert user["phone"] == PHONE
    assert user["username"] == f"phone_{PHONE}"


def test_phone_login_response_shape_matches_password_login(client, hr_user):
    """⚠️ 两种登录的响应**键集合完全相同**（PRD §4.16）。

    前端按 `user.role` 分流的逻辑因此不需要第二套实现。给手机登录另加一个字段
    就会让这条失败 —— 而失败是对的：那意味着前端必须开始区分两条路径。
    """
    password_login = client.post(
        "/api/auth/login", json={"username": "hr_test", "password": "hr12345678"}
    )
    assert password_login.status_code == 200

    code = _send_code(client).json()["dev_code"]
    phone_login = _phone_login(client, PHONE, code)
    assert phone_login.status_code == 200

    assert set(phone_login.json()) == set(password_login.json()) == {"token", "user"}
    assert set(phone_login.json()["user"]) == set(password_login.json()["user"])


def test_phone_login_token_is_usable(client):
    code = _send_code(client).json()["dev_code"]
    token = _phone_login(client, PHONE, code).json()["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["phone"] == PHONE


def test_phone_login_wrong_code_is_401_unified(client):
    """四种失败共用同一句文案（PRD §4.16）—— 不区分即不可探测。"""
    _send_code(client)

    wrong = _phone_login(client, PHONE, "000000")
    never_sent = _phone_login(client, "13900139000", "000000")

    assert wrong.status_code == never_sent.status_code == 401
    assert wrong.json()["code"] == "UNAUTHORIZED"
    assert wrong.json()["message"] == never_sent.json()["message"] == "验证码错误或已失效"


def test_phone_login_as_bound_hr_enters_hr_side(client, admin_headers, hr_user):
    """「全部角色可用」的端到端验证：角色由**绑定**决定（PRD §4.16）。

    HR 账号的手机号只能由 admin 设置 —— 这条路径受 admin 守卫保护，
    因此手机号 → 特权账号的映射由 admin 独家控制。
    """
    bind = client.patch(
        f"/api/users/{hr_user.id}", json={"phone": PHONE}, headers=admin_headers
    )
    assert bind.status_code == 200

    code = _send_code(client).json()["dev_code"]
    resp = _phone_login(client, PHONE, code)

    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "hr"
    assert resp.json()["user"]["id"] == hr_user.id


# ===========================================================================
# 5.5 修改用户 —— 手机号绑定 / 解绑（MVP-5）
# ===========================================================================


def test_patch_user_binds_phone(client, admin_headers, hr_user):
    resp = client.patch(
        f"/api/users/{hr_user.id}", json={"phone": " 138 0013 8000 "}, headers=admin_headers
    )

    assert resp.status_code == 200
    # 归一化后落库：带空格 / 国家码的写法不该产生第二个账号（PRD §4.16）
    assert resp.json()["phone"] == PHONE


def test_patch_user_duplicate_phone_is_409(client, admin_headers, hr_user, other_hr):
    client.patch(f"/api/users/{hr_user.id}", json={"phone": PHONE}, headers=admin_headers)

    resp = client.patch(
        f"/api/users/{other_hr.id}", json={"phone": PHONE}, headers=admin_headers
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert resp.json()["message"] == "该手机号已被占用"


def test_patch_user_phone_null_unbinds(client, admin_headers, hr_user):
    client.patch(f"/api/users/{hr_user.id}", json={"phone": PHONE}, headers=admin_headers)

    resp = client.patch(
        f"/api/users/{hr_user.id}", json={"phone": None}, headers=admin_headers
    )

    assert resp.status_code == 200
    assert resp.json()["phone"] is None


def test_patch_user_omitting_phone_keeps_it(client, admin_headers, hr_user):
    """⚠️「不传 phone」≠「传 null」（PRD §4.1）。

    用 `is not None` 判定会把「不传」也当成「不改」—— 那是对的；但反过来把
    「传 null」当成「不传」就会让解绑静默失效。这条钉住前者，上一条钉住后者。
    """
    client.patch(f"/api/users/{hr_user.id}", json={"phone": PHONE}, headers=admin_headers)

    resp = client.patch(
        f"/api/users/{hr_user.id}", json={"is_active": True}, headers=admin_headers
    )

    assert resp.status_code == 200
    assert resp.json()["phone"] == PHONE  # 未被清空


def test_patch_user_phone_as_hr_is_forbidden(client, hr_headers, other_hr):
    """手机号 → 特权账号的映射只能由 admin 建立。"""
    resp = client.patch(
        f"/api/users/{other_hr.id}", json={"phone": PHONE}, headers=hr_headers
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_admin_can_bind_own_phone(client, admin_headers, admin_user):
    """admin 给自己绑手机号是允许的（PRD §4.16）。

    既有的「不能修改自己的角色或状态」防呆**只拦角色与状态** —— 给自己绑手机号
    不会让任何人失去管理能力，没有理由要求他请另一个 admin 代劳。
    """
    resp = client.patch(
        f"/api/users/{admin_user.id}", json={"phone": PHONE}, headers=admin_headers
    )

    assert resp.status_code == 200
    assert resp.json()["phone"] == PHONE

    # 但改自己的角色仍然被拦（既有行为不变）
    still_blocked = client.patch(
        f"/api/users/{admin_user.id}", json={"role": "hr"}, headers=admin_headers
    )
    assert still_blocked.status_code == 409
