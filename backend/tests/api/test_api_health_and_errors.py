"""API 接口测试 —— 模块 1/9：系统（健康检查）与全局错误信封。

本文件是**跨模块**的：错误信封 `{code, message, detail}` 是全部 8 个业务模块
共同遵守的对外契约，过去只有 `tests/test_health.py` 一处集中断言，其余模块
各自抽查。这里把它按模块逐条钉死，并覆盖三类此前**没有 HTTP 层用例**的行为
（过期 token、换密钥签发的 token、成功响应未被包裹）。

契约来源：
    docs/superpowers/specs/2026-09-15-module-00-core-plan.md §6.2 / §6.3
        —— 错误体恒为三字段；异常 → HTTP → code 的映射表
    docs/apis/API接口文档.md §2.3 / §2.4 —— 对外承诺的响应格式

⚠️ 本文件如实记录了两处**信封例外**（未知路径的 404、方法不对的 405），
   它们由 Starlette 在路由层直接返回，不经过项目的异常处理器。
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings


# ===========================================================================
# 1. 健康检查
# ===========================================================================


def test_health_returns_exact_body(client):
    """响应体**恰好**是 {"status": "ok"} —— 多一个字段也算破坏契约。"""
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_needs_no_auth(client):
    """健康检查不要求 token（是三个公开端点之一）。"""
    assert client.get("/api/health", headers={}).status_code == 200


# ===========================================================================
# 2. 两处信封例外 —— 由 Starlette 在路由层返回，不走项目的异常处理器
# ===========================================================================


def test_unknown_route_response_is_not_wrapped(client):
    """⚠️ 已知例外：路径不存在的 404 **不是**三字段信封。

    `docs/apis/API接口文档.md` 说「所有错误响应共用同一结构」——
    对**应用内**抛出的错误成立，对**路由层**的失败不成立：
    路径拼错时 Starlette 直接返回 `{"detail": "Not Found"}`，
    根本进不到 `handle_app_error`。

    这条用例的价值是把这个事实钉下来：前端写统一错误拦截器时，
    **必须容忍 body 里没有 `code`**，否则前端自己拼错 URL 时会崩在拦截器里。
    """
    resp = client.get("/api/nope")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}
    assert "code" not in resp.json()


def test_wrong_method_response_is_not_wrapped(client):
    """⚠️ 已知例外：方法不对的 405 同样不是三字段信封。"""
    resp = client.delete("/api/health")

    assert resp.status_code == 405
    assert resp.json() == {"detail": "Method Not Allowed"}
    assert "code" not in resp.json()


# ===========================================================================
# 3. 错误信封一致性 —— 每个模块抽一条真实错误路径
# ===========================================================================


def test_error_envelope_is_uniform_across_all_modules(
    client, hr_headers, admin_headers, candidate_headers
):
    """逐模块走一条真实错误路径，断言信封**恰好**是三字段、code 正确。

    覆盖 8 个业务模块：auth / users / position / question / interview /
    evaluation / candidate / resume / practice。任何一处把错误体改成
    FastAPI 默认形状（`{"detail": ...}`）或漏字段，这里都会红。
    """
    cases = [
        # (method, url, headers, json, 期望状态码, 期望 code)
        ("GET", "/api/auth/me", {}, None, 401, "UNAUTHORIZED"),
        (
            "GET",
            "/api/auth/me",
            {"Authorization": "Bearer not-a-jwt"},
            None,
            401,
            "INVALID_TOKEN",
        ),
        ("POST", "/api/auth/login", {}, {"username": "only-username"}, 400, "VALIDATION_ERROR"),
        ("POST", "/api/auth/register", {}, {"username": "x", "password": "short"}, 400, "VALIDATION_ERROR"),
        ("GET", "/api/users", hr_headers, None, 403, "FORBIDDEN"),
        ("GET", "/api/positions/424242", hr_headers, None, 404, "NOT_FOUND"),
        (
            "POST",
            "/api/positions",
            hr_headers,
            {"name": "", "jd": "", "evaluation_dimensions": []},
            400,
            "VALIDATION_ERROR",
        ),
        ("GET", "/api/questions/424242", hr_headers, None, 404, "NOT_FOUND"),
        ("GET", "/api/interviews/424242", hr_headers, None, 404, "NOT_FOUND"),
        ("POST", "/api/interviews/424242/complete", hr_headers, None, 404, "NOT_FOUND"),
        ("GET", "/api/interviews/424242/report", hr_headers, None, 404, "NOT_FOUND"),
        ("POST", "/api/interviews/424242/evaluate", hr_headers, None, 404, "NOT_FOUND"),
        # 候选人侧：HR token 一律 403；candidate token 的资源不存在是 404
        ("GET", "/api/candidate/interviews", hr_headers, None, 403, "FORBIDDEN"),
        ("GET", "/api/candidate/resumes", admin_headers, None, 403, "FORBIDDEN"),
        ("GET", "/api/practice/stats", admin_headers, None, 403, "FORBIDDEN"),
        ("GET", "/api/candidate/resumes/424242", candidate_headers, None, 404, "NOT_FOUND"),
        ("GET", "/api/practice/sessions/424242", candidate_headers, None, 404, "NOT_FOUND"),
    ]

    for method, url, headers, body, want_status, want_code in cases:
        resp = client.request(method, url, headers=headers, json=body)

        where = f"{method} {url}"
        assert resp.status_code == want_status, f"{where} -> {resp.status_code} {resp.text}"

        envelope = resp.json()
        assert set(envelope) == {"code", "message", "detail"}, f"{where} 信封字段不对：{envelope}"
        assert envelope["code"] == want_code, f"{where} code 不对：{envelope['code']}"
        assert isinstance(envelope["message"], str) and envelope["message"], where


def test_validation_error_detail_carries_field_list(client):
    """400 的 `detail.fields[]` 能直接定位到表单项。"""
    resp = client.post("/api/auth/login", json={})

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"

    fields = body["detail"]["fields"]
    assert fields and all({"field", "message", "type"} <= set(f) for f in fields)
    assert {f["field"] for f in fields} == {"username", "password"}


def test_validation_field_messages_are_chinese(client):
    """`detail.fields[].message` 是**中文**，且带出约束值。

    这条不是洁癖：前端 `components/form.js` 的 `fieldErrors().fromServer` 会把
    `message` 原样写进那个字段下方的报错节点 —— 不译的话用户看到的就是
    `String should have at least 8 characters`。译文还要说清该改到多少。
    """
    import re

    resp = client.post(
        "/api/auth/register", json={"username": "someone", "password": "short"}
    )

    assert resp.status_code == 400
    field = next(
        f for f in resp.json()["detail"]["fields"] if f["field"] == "password"
    )
    assert field["type"] == "string_too_short"
    assert "8" in field["message"], field["message"]
    assert re.search(r"[A-Za-z]", field["message"]) is None, (
        f"字段级文案不该是英文原文：{field['message']}"
    )


def test_business_error_envelope_for_duplicate_username(client, admin_headers):
    """409 也是三字段信封（业务冲突不是 500）。"""
    payload = {"username": "dup_user", "password": "dup12345678", "role": "hr"}
    assert client.post("/api/users", json=payload, headers=admin_headers).status_code == 201

    resp = client.post("/api/users", json=payload, headers=admin_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_state_transition_conflict_detail_has_from_and_to(client, hr_headers, position):
    """状态机冲突的 409 带结构化 `detail = {from, to}`。"""
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    # ongoing 下回退 → 非法迁移
    resp = client.post(f"/api/interviews/{interview['id']}/rollback", headers=hr_headers)

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "BUSINESS_ERROR"
    assert body["detail"]["from"] == "ongoing"
    assert body["detail"]["to"] == "ongoing"


# ===========================================================================
# 4. 401 的两种 code 必须分得开（此前只有「格式错误」一种有 HTTP 用例）
# ===========================================================================


def _encode(payload: dict, secret: str) -> str:
    settings = get_settings()
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def test_missing_token_is_unauthorized(client):
    """没带头 → `UNAUTHORIZED`（前端应跳登录）。"""
    resp = client.get("/api/auth/me", headers={})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


def test_expired_token_is_invalid_token(client, hr_user):
    """⚠️ 补空白：过期 token → `INVALID_TOKEN`，与「没带 token」区分开。

    此前该行为只在 `test_security.py` 的**单元层**被断言，HTTP 层从未覆盖，
    但 `API接口文档.md` §2.2 已对外承诺了这条区分。文档承诺了就要有接口层用例。
    """
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=1)
    token = _encode(
        {"sub": str(hr_user.id), "iat": past - timedelta(hours=1), "exp": past},
        settings.jwt_secret,
    )

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_TOKEN"


def test_token_signed_with_other_secret_is_invalid_token(client, hr_user):
    """⚠️ 补空白：换密钥签发的 token → `INVALID_TOKEN`（签名校验真的在跑）。"""
    settings = get_settings()
    now = datetime.now(UTC)
    token = _encode(
        {"sub": str(hr_user.id), "iat": now, "exp": now + timedelta(hours=1)},
        settings.jwt_secret + "-tampered",
    )

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_TOKEN"


def test_tampered_payload_is_invalid_token(client):
    """签名不变、载荷被改写 → 必须拒绝（防「改 sub 冒充他人」）。"""
    settings = get_settings()
    now = datetime.now(UTC)
    good = _encode(
        {"sub": "1", "iat": now, "exp": now + timedelta(hours=1)}, settings.jwt_secret
    )
    head, payload, signature = good.split(".")
    tampered = f"{head}.{payload[:-2]}XX.{signature}"

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_TOKEN"


# ===========================================================================
# 5. 成功响应**不**套信封（此前没有任何用例断言过这一点）
# ===========================================================================


def test_success_responses_are_not_wrapped(client, hr_headers, position):
    """成功响应是裸对象 / 裸数组，**没有** `code` / `data` 之类的包装。

    此前只断言过「错误是三字段」，从未断言「成功不是三字段」——
    若哪天有人给成功响应套一层 `{code, message, data}`，前端会全线崩，
    而旧用例一条都不会红。这条就是防这个。
    """
    single = client.get(f"/api/positions/{position.id}", headers=hr_headers)
    assert single.status_code == 200
    assert isinstance(single.json(), dict)
    assert "code" not in single.json()
    assert "data" not in single.json()

    listing = client.get("/api/positions", headers=hr_headers)
    assert listing.status_code == 200
    assert isinstance(listing.json(), list), "列表接口直接返回数组，不是 {items: [...]}"


# ===========================================================================
# 6. 守卫先于请求体校验
# ===========================================================================


def test_role_guard_precedes_body_validation(client, candidate_headers):
    """角色不符时返回 403 而不是 400 —— **即使请求体是空的**。

    这决定了前端提示什么：403 是「你没权限」，400 是「你参数错了」。
    若顺序反了，候选人拿 HR 接口会收到一堆「参数不合法」，误导排查方向。
    """
    resp = client.post("/api/positions", json={}, headers=candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_path_param_type_error_is_validation_error(client, hr_headers):
    """路径参数类型不对（`abc` 当 id）→ 400 `VALIDATION_ERROR`。

    注意这与上一条并不矛盾：**守卫先跑**，所以无 token 时是 401；
    带了合法 HR token 之后才轮到参数校验，此时才是 400。
    """
    resp = client.post("/api/interviews/abc/complete", headers=hr_headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


# ===========================================================================
# 7. 未预期异常：500 且不泄漏堆栈
# ===========================================================================


def test_unhandled_exception_is_internal_error_without_stacktrace(client):
    """500 是三字段信封，且**响应体不含堆栈或异常原文**。

    用一条本文件独有的路径（`..._envelope`）注册，避免与
    `tests/test_health.py::test_unhandled_exception_shape` 的同名路由互相干扰。
    """
    from app.main import app

    @app.get("/api/_test_unhandled_envelope")
    def _boom():  # pragma: no cover - 仅为触发异常
        raise RuntimeError("internal secret that must not leak")

    resp = client.get("/api/_test_unhandled_envelope")

    assert resp.status_code == 500
    body = resp.json()
    assert set(body) == {"code", "message", "detail"}
    assert body["code"] == "INTERNAL_ERROR"
    assert body["detail"] is None
    assert "Traceback" not in resp.text
    assert "internal secret that must not leak" not in resp.text


# ===========================================================================
# 8. 错误码取值受控：不存在表外的 code
# ===========================================================================

ALLOWED_CODES = {
    "VALIDATION_ERROR",
    "UNAUTHORIZED",
    "INVALID_TOKEN",
    "FORBIDDEN",
    "NOT_FOUND",
    "BUSINESS_ERROR",
    "INTERNAL_ERROR",
    "AI_PROVIDER_ERROR",
}


@pytest.mark.parametrize(
    "method,url,json_body",
    [
        ("GET", "/api/auth/me", None),
        ("GET", "/api/positions/424242", None),
        ("POST", "/api/auth/login", {}),
        ("GET", "/api/nope", None),
    ],
)
def test_error_codes_stay_within_the_documented_set(client, method, url, json_body):
    """任何错误响应里的 `code` 都必须是文档里那 8 个之一。

    注意最后一条（未知路径）的 body 是 Starlette 的 `{detail: ...}`，
    它的 `code` 是缺失而不是越界 —— 因此这里断言「若有 code 则必须合法」，
    用来防止某天有人随手加一个自定义 code 却忘了更新文档与前端分支。
    """
    resp = client.request(method, url, json=json_body)
    body = resp.json()

    if "code" in body:
        assert body["code"] in ALLOWED_CODES, f"{method} {url} 出现了表外的 code：{body['code']}"
