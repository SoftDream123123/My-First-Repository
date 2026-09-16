"""auth 模块测试：登录、JWT、用户管理、数据隔离。"""

from app.auth import repository
from app.auth.models import User

# ------------------------------- 登录 -------------------------------


class TestLogin:
    def test_login_success(self, client, hr_user):
        resp = client.post(
            "/api/auth/login",
            json={"username": "hr_test", "password": "hr12345678"},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["token"]
        assert body["user"]["username"] == "hr_test"
        assert body["user"]["role"] == "hr"
        assert "password_hash" not in body["user"]

    def test_login_wrong_password(self, client, hr_user):
        resp = client.post(
            "/api/auth/login", json={"username": "hr_test", "password": "wrong"}
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"

    def test_login_unknown_username_identical_to_wrong_password(self, client, hr_user):
        """未知用户名与密码错误必须返回完全一致的响应，避免用户名枚举。"""
        wrong_pwd = client.post(
            "/api/auth/login", json={"username": "hr_test", "password": "wrong"}
        )
        unknown = client.post(
            "/api/auth/login", json={"username": "nobody", "password": "wrong"}
        )
        assert wrong_pwd.status_code == unknown.status_code == 401
        assert wrong_pwd.json() == unknown.json()

    def test_login_disabled_user(self, client, hr_user, db):
        hr_user.is_active = False
        db.commit()

        resp = client.post(
            "/api/auth/login",
            json={"username": "hr_test", "password": "hr12345678"},
        )
        assert resp.status_code == 401
        assert resp.json()["message"] == "账号已禁用，请联系管理员"

    def test_password_stored_hashed(self, client, hr_user, db):
        stored = repository.get_by_username(db, "hr_test")
        assert stored.password_hash != "hr12345678"
        assert stored.password_hash.startswith("$2b$")


# ---------------------------- 当前用户 ----------------------------


class TestMe:
    def test_me_with_valid_token(self, client, hr_user, hr_headers):
        resp = client.get("/api/auth/me", headers=hr_headers)
        assert resp.status_code == 200

        body = resp.json()
        assert body["id"] == hr_user.id
        assert body["username"] == "hr_test"
        assert "password_hash" not in body

    def test_me_without_token(self, client):
        assert client.get("/api/auth/me").status_code == 401


# ---------------------------- 用户管理 ----------------------------


class TestUserManagement:
    def test_create_user_as_admin(self, client, admin_headers, db):
        resp = client.post(
            "/api/users",
            json={"username": "new_hr", "password": "password123", "role": "hr"},
            headers=admin_headers,
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["username"] == "new_hr"
        assert body["role"] == "hr"
        assert body["is_active"] is True
        assert "password_hash" not in body

        # MySQL 默认 REPEATABLE READ：db 夹具的事务快照早于上面那次 HTTP 请求的
        # 提交，必须先结束当前事务，否则读到的是旧快照。
        db.rollback()

        created = repository.get_by_username(db, "new_hr")
        assert created is not None
        assert created.password_hash.startswith("$2b$")

    def test_create_user_as_hr_forbidden(self, client, hr_headers):
        resp = client.post(
            "/api/users",
            json={"username": "x", "password": "password123", "role": "hr"},
            headers=hr_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_create_user_without_token(self, client):
        resp = client.post(
            "/api/users",
            json={"username": "x", "password": "password123", "role": "hr"},
        )
        assert resp.status_code == 401

    def test_create_user_duplicate_username(self, client, admin_headers, hr_user):
        resp = client.post(
            "/api/users",
            json={"username": "hr_test", "password": "password123", "role": "hr"},
            headers=admin_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    def test_create_user_short_password(self, client, admin_headers):
        resp = client.post(
            "/api/users",
            json={"username": "short_pwd", "password": "1234567", "role": "hr"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"

    def test_create_user_invalid_role(self, client, admin_headers):
        resp = client.post(
            "/api/users",
            json={"username": "bad_role", "password": "password123", "role": "boss"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_list_users_as_admin(self, client, admin_headers, hr_user):
        resp = client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 200

        users = resp.json()
        assert len(users) >= 2
        assert all("password_hash" not in u for u in users)

    def test_list_users_as_hr_forbidden(self, client, hr_headers):
        assert client.get("/api/users", headers=hr_headers).status_code == 403

    def test_update_user_role(self, client, admin_headers, hr_user):
        resp = client.patch(
            f"/api/users/{hr_user.id}", json={"role": "admin"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_update_user_disable_then_login_fails(self, client, admin_headers, hr_user):
        resp = client.patch(
            f"/api/users/{hr_user.id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        login = client.post(
            "/api/auth/login",
            json={"username": "hr_test", "password": "hr12345678"},
        )
        assert login.status_code == 401

    def test_update_nonexistent_user(self, client, admin_headers):
        resp = client.patch(
            "/api/users/999999", json={"role": "hr"}, headers=admin_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_admin_cannot_modify_self(self, client, admin_user, admin_headers):
        resp = client.patch(
            f"/api/users/{admin_user.id}", json={"role": "hr"}, headers=admin_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    def test_admin_cannot_disable_self(self, client, admin_user, admin_headers):
        resp = client.patch(
            f"/api/users/{admin_user.id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_role_change_takes_effect_immediately(self, client, admin_headers, hr_user, hr_headers):
        """hr 升级为 admin 后，用同一个旧 token 即可访问 /users。"""
        assert client.get("/api/users", headers=hr_headers).status_code == 403

        client.patch(
            f"/api/users/{hr_user.id}", json={"role": "admin"}, headers=admin_headers
        )

        assert client.get("/api/users", headers=hr_headers).status_code == 200


# --------------------------- 响应脱敏检查 ---------------------------


def test_all_user_responses_exclude_password_hash(client, admin_headers, hr_user):
    """三个用户相关端点的响应体中均不得出现 password_hash。"""
    responses = [
        client.post(
            "/api/auth/login",
            json={"username": "hr_test", "password": "hr12345678"},
        ),
        client.get("/api/auth/me", headers=admin_headers),
        client.get("/api/users", headers=admin_headers),
        client.post(
            "/api/users",
            json={"username": "fresh_user", "password": "password123", "role": "hr"},
            headers=admin_headers,
        ),
    ]
    for resp in responses:
        assert "password_hash" not in resp.text


def test_user_model_repr_does_not_leak_hash(hr_user):
    assert "password_hash" not in repr(hr_user)
    assert "hr12345678" not in repr(hr_user)


def test_user_query_returns_model_instance(db, hr_user):
    fetched = repository.get_by_id(db, hr_user.id)
    assert isinstance(fetched, User)
    assert fetched.id == hr_user.id
