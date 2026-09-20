"""core.deps 依赖注入测试。"""

import pytest

from app.auth.models import User
from app.auth.service import scope_owner_id
from app.core.deps import require_role, require_roles
from app.core.exceptions import ForbiddenError


class TestGetCurrentUser:
    def test_missing_header(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"

    def test_bad_scheme(self, client):
        resp = client.get(
            "/api/auth/me", headers={"Authorization": "Token not-a-bearer"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"

    def test_empty_bearer_value(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_invalid_token(self, client):
        resp = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_valid_token(self, client, hr_user, hr_headers):
        resp = client.get("/api/auth/me", headers=hr_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == hr_user.username

    def test_token_of_nonexistent_user(self, client):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(999999)}"}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_disabled_user_rejected(self, client, hr_user, hr_headers, db):
        """账号被禁用后，其旧 token 立即失效（角色 / 状态不缓存于 JWT）。"""
        assert client.get("/api/auth/me", headers=hr_headers).status_code == 200

        hr_user.is_active = False
        db.commit()

        assert client.get("/api/auth/me", headers=hr_headers).status_code == 401


class TestRequireRole:
    def test_admin_passes(self, client, admin_headers):
        assert client.get("/api/users", headers=admin_headers).status_code == 200

    def test_hr_rejected(self, client, hr_headers):
        resp = client.get("/api/users", headers=hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"


class TestScopeOwnerId:
    def test_admin_returns_none(self, admin_user):
        assert scope_owner_id(admin_user) is None

    def test_hr_returns_own_id(self, hr_user):
        assert scope_owner_id(hr_user) == hr_user.id

    def test_unknown_role_treated_as_restricted(self):
        """非 admin 的一律按受限处理（白名单而非黑名单）。"""
        fake = User(id=123, username="x", password_hash="x", role="hr")
        assert scope_owner_id(fake) == 123


class TestRequireRoles:
    """多角色守卫（module-09 §4.5）。

    直接调用依赖函数并显式传入 user —— 其 user 参数的默认值是
    Depends(get_current_user)，显式传参即绕过 FastAPI 的依赖求解。
    """

    def test_require_roles_single_pass(self, hr_user):
        assert require_roles("hr")(user=hr_user) is hr_user

    def test_require_roles_multi_pass_admin(self, admin_user):
        assert require_roles("admin", "hr")(user=admin_user) is admin_user

    def test_require_roles_multi_pass_hr(self, hr_user):
        assert require_roles("admin", "hr")(user=hr_user) is hr_user

    def test_require_roles_reject_candidate_on_hr_guard(self, candidate_user):
        with pytest.raises(ForbiddenError):
            require_roles("admin", "hr")(user=candidate_user)

    def test_require_roles_reject_admin_on_candidate_guard(self, admin_user):
        """候选人侧守卫**精确匹配** —— admin 在其中不通行。

        候选人是终端用户角色，admin 无正当理由代其刷题或作答；一旦放行
        就会污染候选人的练习数据与作答归属。
        """
        with pytest.raises(ForbiddenError):
            require_roles("candidate")(user=admin_user)

    def test_require_roles_reject_hr_on_candidate_guard(self, hr_user):
        with pytest.raises(ForbiddenError):
            require_roles("candidate")(user=hr_user)

    def test_require_role_still_equals_require_roles(self, admin_user, hr_user):
        """薄封装未走样：两者行为一致。"""
        assert require_role("admin")(user=admin_user) is admin_user

        with pytest.raises(ForbiddenError):
            require_role("admin")(user=hr_user)

    def test_require_roles_requires_auth(self, client, position):
        """守卫不绕过登录校验：无 token → 401 而非 403。"""
        resp = client.get("/api/positions")
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"
