"""API 接口测试 —— 模块 2/9：auth（登录 / 自助注册 / 当前用户 / 用户管理）。

覆盖 6 个 method-route：
    POST   /api/auth/login
    POST   /api/auth/register
    GET    /api/auth/me
    POST   /api/users
    GET    /api/users
    PATCH  /api/users/{user_id}

契约来源：
    docs/superpowers/specs/2026-09-15-module-01-auth-plan.md
    docs/superpowers/specs/2026-09-20-module-09-auth-plan.md  §4.1 / §4.2 / §4.5
    docs/apis/API接口文档.md §5.1–§5.6

本文件补齐了几处此前没有 HTTP 层用例的边界：`PATCH /users` 的非法 role 与空请求体、
`POST /users` 的用户名超长、登录/注册夹带未知字段。
"""

import pytest

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
    assert set(body) == {"id", "username", "role", "is_active", "created_at"}


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
