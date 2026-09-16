"""position 模块测试：鉴权、数据隔离、维度校验、CRUD、删除保护。"""

import pytest

from app.core.security import create_access_token

VALID_DIMS = ["沟通能力", "专业能力", "逻辑思维", "文化契合"]


def _create(client, headers, name="后端工程师", dims=None, jd="负责后端服务开发"):
    return client.post(
        "/api/positions",
        json={
            "name": name,
            "jd": jd,
            "evaluation_dimensions": dims if dims is not None else VALID_DIMS,
        },
        headers=headers,
    )


@pytest.fixture
def other_hr(db):
    from app.auth import service

    return service.create_user(db, "hr_other", "hr12345678", "hr")


@pytest.fixture
def other_hr_headers(other_hr) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_hr.id)}"}


# --------------------------- 鉴权与隔离 ---------------------------


class TestAuthAndIsolation:
    def test_create_without_token(self, client):
        assert _create(client, {}).status_code == 401

    def test_create_ok(self, client, hr_headers, hr_user):
        resp = _create(client, hr_headers)
        assert resp.status_code == 201

        body = resp.json()
        assert body["id"]
        assert body["name"] == "后端工程师"
        assert body["created_by"] == hr_user.id
        assert body["evaluation_dimensions"] == VALID_DIMS

    def test_list_only_own_positions(self, client, hr_headers, other_hr_headers):
        _create(client, hr_headers, name="岗位A")
        _create(client, other_hr_headers, name="岗位B")

        mine = client.get("/api/positions", headers=hr_headers).json()
        theirs = client.get("/api/positions", headers=other_hr_headers).json()

        assert [p["name"] for p in mine] == ["岗位A"]
        assert [p["name"] for p in theirs] == ["岗位B"]

    def test_admin_sees_all_positions(
        self, client, hr_headers, other_hr_headers, admin_headers
    ):
        _create(client, hr_headers, name="岗位A")
        _create(client, other_hr_headers, name="岗位B")

        all_positions = client.get("/api/positions", headers=admin_headers).json()
        assert {p["name"] for p in all_positions} == {"岗位A", "岗位B"}

    def test_get_other_users_position_forbidden(
        self, client, hr_headers, other_hr_headers
    ):
        position_id = _create(client, hr_headers).json()["id"]
        resp = client.get(f"/api/positions/{position_id}", headers=other_hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_get_nonexistent_position(self, client, hr_headers):
        resp = client.get("/api/positions/999999", headers=hr_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_update_other_users_position_forbidden(
        self, client, hr_headers, other_hr_headers
    ):
        position_id = _create(client, hr_headers).json()["id"]
        resp = client.put(
            f"/api/positions/{position_id}",
            json={"name": "改名", "jd": "x", "evaluation_dimensions": ["A"]},
            headers=other_hr_headers,
        )
        assert resp.status_code == 403

    def test_delete_other_users_position_forbidden(
        self, client, hr_headers, other_hr_headers
    ):
        position_id = _create(client, hr_headers).json()["id"]
        resp = client.delete(
            f"/api/positions/{position_id}", headers=other_hr_headers
        )
        assert resp.status_code == 403


# ----------------------------- 维度校验 -----------------------------


class TestDimensionValidation:
    def test_empty_dimensions(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=[])
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"

    def test_too_many_dimensions(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=[f"维度{i}" for i in range(11)])
        assert resp.status_code == 400

    def test_exactly_ten_dimensions_ok(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=[f"维度{i}" for i in range(10)])
        assert resp.status_code == 201

    def test_duplicate_dimensions(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=["沟通", "沟通"])
        assert resp.status_code == 400

    def test_duplicate_dimensions_case_insensitive(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=["Communication", "communication"])
        assert resp.status_code == 400

    def test_duplicate_dimensions_whitespace(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=[" 沟通 ", "沟通"])
        assert resp.status_code == 400

    def test_dimension_too_long(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=["字" * 51])
        assert resp.status_code == 400

    def test_dimension_exactly_50_chars_ok(self, client, hr_headers):
        assert _create(client, hr_headers, dims=["字" * 50]).status_code == 201

    def test_empty_string_dimension(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=["   "])
        assert resp.status_code == 400

    def test_dimensions_stored_stripped(self, client, hr_headers):
        resp = _create(client, hr_headers, dims=[" 沟通 ", "Communication"])
        assert resp.status_code == 201
        assert resp.json()["evaluation_dimensions"] == ["沟通", "Communication"]


# ------------------------------ CRUD ------------------------------


class TestCrud:
    def test_duplicate_name_same_owner(self, client, hr_headers):
        assert _create(client, hr_headers, name="同名").status_code == 201
        resp = _create(client, hr_headers, name="同名")
        assert resp.status_code == 409
        assert resp.json()["code"] == "BUSINESS_ERROR"

    def test_same_name_different_owner_allowed(
        self, client, hr_headers, other_hr_headers
    ):
        assert _create(client, hr_headers, name="同名").status_code == 201
        assert _create(client, other_hr_headers, name="同名").status_code == 201

    def test_update_position(self, client, hr_headers):
        position_id = _create(client, hr_headers).json()["id"]

        resp = client.put(
            f"/api/positions/{position_id}",
            json={
                "name": "新名称",
                "jd": "新 JD",
                "evaluation_dimensions": ["新维度"],
            },
            headers=hr_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["name"] == "新名称"
        assert body["jd"] == "新 JD"
        assert body["evaluation_dimensions"] == ["新维度"]

    def test_update_duplicate_name(self, client, hr_headers):
        _create(client, hr_headers, name="岗位A")
        position_id = _create(client, hr_headers, name="岗位B").json()["id"]

        resp = client.put(
            f"/api/positions/{position_id}",
            json={"name": "岗位A", "jd": "x", "evaluation_dimensions": ["A"]},
            headers=hr_headers,
        )
        assert resp.status_code == 409

    def test_update_with_own_name_is_allowed(self, client, hr_headers):
        """改成自己原有的名字不算冲突。"""
        position_id = _create(client, hr_headers, name="岗位A").json()["id"]
        resp = client.put(
            f"/api/positions/{position_id}",
            json={"name": "岗位A", "jd": "改过的 JD", "evaluation_dimensions": ["A"]},
            headers=hr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["jd"] == "改过的 JD"

    def test_update_dimensions_replaces_not_appends(self, client, hr_headers):
        position_id = _create(client, hr_headers, dims=["A", "B"]).json()["id"]

        resp = client.put(
            f"/api/positions/{position_id}",
            json={"name": "后端工程师", "jd": "x", "evaluation_dimensions": ["C"]},
            headers=hr_headers,
        )
        assert resp.json()["evaluation_dimensions"] == ["C"]

    def test_delete_ok(self, client, hr_headers):
        position_id = _create(client, hr_headers).json()["id"]

        resp = client.delete(f"/api/positions/{position_id}", headers=hr_headers)
        assert resp.status_code == 204
        assert resp.content == b""

        assert (
            client.get(f"/api/positions/{position_id}", headers=hr_headers).status_code
            == 404
        )

    def test_list_with_keyword(self, client, hr_headers):
        _create(client, hr_headers, name="后端工程师")
        _create(client, hr_headers, name="前端工程师")
        _create(client, hr_headers, name="产品经理")

        resp = client.get("/api/positions?keyword=工程师", headers=hr_headers)
        names = {p["name"] for p in resp.json()}
        assert names == {"后端工程师", "前端工程师"}

    def test_jd_too_long(self, client, hr_headers):
        assert _create(client, hr_headers, jd="字" * 10001).status_code == 400

    def test_name_empty(self, client, hr_headers):
        assert _create(client, hr_headers, name="").status_code == 400

    def test_list_ordered_by_id(self, client, hr_headers):
        for name in ["甲", "乙", "丙"]:
            _create(client, hr_headers, name=name)
        ids = [p["id"] for p in client.get("/api/positions", headers=hr_headers).json()]
        assert ids == sorted(ids)
