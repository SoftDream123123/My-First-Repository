"""core.deps 依赖注入测试。"""

from app.auth.models import User
from app.auth.service import scope_owner_id


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
