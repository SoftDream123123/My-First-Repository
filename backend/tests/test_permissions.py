"""权限守卫测试（计划书 module-16 §7）。

分四组：
  A. 自维护不变量 —— 遍历 app.routes，随新端点自动扩展
  B. 角色矩阵 —— 存量端点逐组断言（含 hr/admin 的反向断言）
  C. scope_owner_id 纵深防御
  D. SSE 端点「先拒绝再建流」

A 组是本文档最重要的两条：它们不写死端点清单，因此将来有人新增 HR 端点却
忘挂守卫时，测试会立刻失败。手抄清单在端点增删后必然失效 —— 那正是本模块
要修的那类「静默漏掉一处」的问题。
"""

import re

import pytest

from app.auth.service import ensure_resource_visible, scope_owner_id
from app.core.exceptions import ForbiddenError

# 候选人 token 不应触及的任何 HR 侧路径前缀
HR_PATH_PREFIXES = (
    "/api/positions",
    "/api/questions",
    "/api/interviews",
    "/api/users",
)

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_PATH_PARAM = re.compile(r"\{[^}]+\}")


def _iter_routes(prefixes: tuple[str, ...]):
    """遍历 app.routes，产出 (method, 已替换路径参数的路径)。

    路径参数统一替换为 999999：这些路由的守卫在依赖阶段就应生效，
    因此不需要真实资源存在。
    """
    from app.main import app

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue  # 跳过 Mount（/assets）等无方法的条目

        if not path.startswith(prefixes):
            continue

        concrete = _PATH_PARAM.sub("999999", path)
        for method in sorted(methods & _HTTP_METHODS):
            yield method, concrete


# ---------------------- A. 自维护不变量 ----------------------


def test_no_hr_route_reachable_by_candidate(client, candidate_headers):
    """候选人 token 对任何 HR 侧路由都必须恒为 403，且不存在任何 2xx。"""
    reachable = []
    for method, path in _iter_routes(HR_PATH_PREFIXES):
        resp = client.request(method, path, json={}, headers=candidate_headers)
        if resp.status_code != 403:
            reachable.append(f"{method} {path} -> {resp.status_code}")

    assert not reachable, (
        "以下 HR 侧路由未挂角色守卫（候选人可达）：\n  " + "\n  ".join(reachable)
    )


def test_no_hr_route_reachable_by_hr(client, hr_headers):
    """`/api/users*` 是 admin 专属，hr token 必须恒 403。"""
    reachable = []
    for method, path in _iter_routes(("/api/users",)):
        resp = client.request(method, path, json={}, headers=hr_headers)
        if resp.status_code != 403:
            reachable.append(f"{method} {path} -> {resp.status_code}")

    assert not reachable, (
        "以下 admin 专属路由对 hr 可达：\n  " + "\n  ".join(reachable)
    )


# ---------------------- B. 角色矩阵 ----------------------


class TestCandidateRejected:
    def test_position_endpoints_reject_candidate(self, client, candidate_headers):
        for method, path in _iter_routes(("/api/positions",)):
            assert client.request(
                method, path, json={}, headers=candidate_headers
            ).status_code == 403

    def test_question_endpoints_reject_candidate(self, client, candidate_headers):
        for method, path in _iter_routes(("/api/questions",)):
            assert client.request(
                method, path, json={}, headers=candidate_headers
            ).status_code == 403

    def test_interview_endpoints_reject_candidate(self, client, candidate_headers):
        for method, path in _iter_routes(("/api/interviews",)):
            assert client.request(
                method, path, json={}, headers=candidate_headers
            ).status_code == 403

    def test_evaluation_endpoints_reject_candidate(self, client, candidate_headers):
        """评估三端点（触发、SSE 流、报告）都在 /api/interviews 前缀下。"""
        endpoints = [
            ("POST", "/api/interviews/999999/evaluate"),
            ("GET", "/api/interviews/999999/evaluation/stream"),
            ("GET", "/api/interviews/999999/report"),
        ]
        for method, path in endpoints:
            resp = client.request(method, path, json={}, headers=candidate_headers)
            assert resp.status_code == 403, f"{method} {path} 未拒绝候选人"


class TestHrAndAdminPass:
    """反向断言：只测「候选人被拒」会掩盖「守卫把 hr 也拒了」这类过度收紧。"""

    def test_hr_passes_hr_guards(self, client, hr_headers):
        # 取每条路径组一个不需要预置数据的端点
        assert client.get("/api/positions", headers=hr_headers).status_code == 200
        assert client.get("/api/questions", headers=hr_headers).status_code == 200
        assert client.get("/api/interviews", headers=hr_headers).status_code == 200
        # 资源不存在应得 404 而非 403 —— 证明确实进了 service 层
        assert (
            client.get("/api/interviews/999999", headers=hr_headers).status_code == 404
        )

    def test_admin_passes_hr_guards(self, client, admin_headers):
        assert client.get("/api/positions", headers=admin_headers).status_code == 200
        assert client.get("/api/questions", headers=admin_headers).status_code == 200
        assert client.get("/api/interviews", headers=admin_headers).status_code == 200

    def test_hr_rejected_on_admin_only_users(self, client, hr_headers):
        resp = client.get("/api/users", headers=hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"


# ---------------------- C. scope_owner_id 纵深防御 ----------------------


class TestScopeOwnerIdDefense:
    def test_scope_owner_id_candidate_raises(self, candidate_user):
        """候选人到达此处必须抛错。

        两种「更温和」的写法都更糟：返回 None 等于不过滤（候选人看到全部数据），
        返回 user.id 等于把候选人伪造成资源创建者。
        """
        with pytest.raises(ForbiddenError):
            scope_owner_id(candidate_user)

    def test_scope_owner_id_hr_returns_id(self, hr_user):
        assert scope_owner_id(hr_user) == hr_user.id

    def test_scope_owner_id_admin_returns_none(self, admin_user):
        assert scope_owner_id(admin_user) is None

    def test_ensure_resource_visible_rejects_candidate(self, candidate_user):
        with pytest.raises(ForbiddenError):
            ensure_resource_visible(candidate_user, 1, "岗位")


# ---------------------- D. SSE 端点 ----------------------


def _create_interview(client, headers, position_id, name="张三"):
    return client.post(
        "/api/interviews",
        json={"position_id": position_id, "candidate_name": name},
        headers=headers,
    )


class TestSseGuard:
    def test_stream_rejects_candidate(self, client, candidate_headers):
        """守卫必须在**建立流之前**生效 —— 不能先开流再拒。"""
        resp = client.get(
            "/api/interviews/999999/evaluation/stream", headers=candidate_headers
        )
        assert resp.status_code == 403
        assert "text/event-stream" not in resp.headers.get("content-type", "")

    def test_stream_rejects_hr_for_others_interview(
        self, client, hr_headers, other_hr_headers, position
    ):
        created = _create_interview(client, hr_headers, position.id)
        interview_id = created.json()["id"]

        resp = client.get(
            f"/api/interviews/{interview_id}/evaluation/stream",
            headers=other_hr_headers,
        )
        assert resp.status_code == 403
        assert "text/event-stream" not in resp.headers.get("content-type", "")
