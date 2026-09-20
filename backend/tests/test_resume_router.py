"""resume 模块端点、鉴权与隔离测试（计划书 module-17 §7.2 / §7.6）。

五个端点全部守卫 `require_roles("candidate")`：hr 与 admin 在候选人侧**都不通行**
（module-09 §4.5 的精确匹配规则），因此两组都要逐端点断言。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update as sa_update

from app.core.config import get_settings
from app.resume import repository
from app.resume.models import Resume

URL = "/api/candidate/resumes"

RESUME_ENDPOINTS = [
    ("POST", URL),
    ("GET", URL),
    ("GET", f"{URL}/999999"),
    ("PUT", f"{URL}/999999"),
    ("DELETE", f"{URL}/999999"),
]


def _create_via_api(client, headers, **overrides):
    payload = {"title": "张三-后端开发", "content": "五年 Python 后端经验。"}
    payload.update(overrides)
    resp = client.post(URL, json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _fresh(db) -> None:
    """结束当前事务，让随后的读能看到别的连接刚提交的数据（REPEATABLE READ）。"""
    db.rollback()


def _backdate(db, resume_id: int, when: datetime) -> None:
    """把 created_at / updated_at 压到指定时刻。

    DATETIME 是**秒精度**：同一秒内写入的两行无法区分先后。凡是需要断言
    「谁在前」的用例，都先制造两个可区分的历史时刻（而不是 sleep 一秒 ——
    那是时间竞态，机器一卡就红）。
    """
    db.execute(
        sa_update(Resume)
        .where(Resume.id == resume_id)
        .values(created_at=when, updated_at=when)
    )
    db.commit()


# ==================== 鉴权（§7.6）====================


class TestAuth:
    @pytest.mark.parametrize("method,path", RESUME_ENDPOINTS)
    def test_rejects_hr(self, client, hr_headers, method, path):
        resp = client.request(method, path, json={}, headers=hr_headers)
        assert resp.status_code == 403, f"{method} {path} 未拒绝 hr"
        assert resp.json()["code"] == "FORBIDDEN"

    @pytest.mark.parametrize("method,path", RESUME_ENDPOINTS)
    def test_rejects_admin(self, client, admin_headers, method, path):
        """admin 在候选人侧同样不通行 —— 放行会污染候选人的简历归属。"""
        resp = client.request(method, path, json={}, headers=admin_headers)
        assert resp.status_code == 403, f"{method} {path} 未拒绝 admin"

    @pytest.mark.parametrize("method,path", RESUME_ENDPOINTS)
    def test_rejects_anonymous(self, client, method, path):
        resp = client.request(method, path, json={})
        assert resp.status_code == 401

    def test_hr_token_on_candidate_path_is_forbidden_not_authenticated(
        self, client, hr_headers
    ):
        """HR 是合法登录用户，但仍不得被当作候选人放行。"""
        resp = client.get(URL, headers=hr_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"


# ==================== 新建（§7.1 / §7.2）====================


class TestCreateEndpoint:
    def test_create_ok(self, client, candidate_headers):
        body = _create_via_api(client, candidate_headers)

        assert body["id"] > 0
        assert body["title"] == "张三-后端开发"
        assert body["content"] == "五年 Python 后端经验。"
        assert body["candidate_name"] is None
        assert body["candidate_contact"] is None
        assert "created_by" not in body
        assert body["created_at"] and body["updated_at"]

    def test_created_by_comes_from_token(self, client, db, candidate_user, candidate_headers):
        """请求体里塞 created_by 也不会被采纳（字段不存在，直接忽略）。"""
        body = _create_via_api(client, candidate_headers, **{"created_by": 999999})

        _fresh(db)
        row = repository.get_by_id(db, body["id"])
        assert row.created_by == candidate_user.id

    def test_blank_title_is_400(self, client, candidate_headers):
        resp = client.post(
            URL, json={"title": "   ", "content": "正文"}, headers=candidate_headers
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"
        assert resp.json()["detail"]["fields"][0]["field"] == "title"

    def test_content_over_limit_is_422(self, client, candidate_headers):
        limit = get_settings().resume_content_max_length
        resp = client.post(
            URL,
            json={"title": "超长简历", "content": "正" * (limit + 1)},
            headers=candidate_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "VALIDATION_ERROR"

    def test_content_at_limit_is_201(self, client, candidate_headers):
        limit = get_settings().resume_content_max_length
        body = _create_via_api(client, candidate_headers, content="正" * limit)
        assert len(body["content"]) == limit

    def test_duplicate_title_allowed(self, client, candidate_headers):
        first = _create_via_api(client, candidate_headers, title="通用简历")
        second = _create_via_api(client, candidate_headers, title="通用简历")
        assert first["id"] != second["id"]


# ==================== 列表（§7.2）====================


class TestListEndpoint:
    def test_only_own(self, client, candidate_headers, other_candidate_headers, resume):
        _create_via_api(client, other_candidate_headers, title="别人的简历")

        listed = client.get(URL, headers=candidate_headers).json()
        assert [item["id"] for item in listed] == [resume.id]

    def test_empty_returns_empty_array(self, client, candidate_headers):
        resp = client.get(URL, headers=candidate_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_capped(self, client, candidate_headers):
        """超上限直接报错，不静默截断 —— 静默截断会让调用方以为拿全了。"""
        resp = client.get(URL, params={"limit": 201}, headers=candidate_headers)
        assert resp.status_code == 400

    def test_response_excludes_created_by(self, client, candidate_headers, resume):
        listed = client.get(URL, headers=candidate_headers).json()
        assert "created_by" not in listed[0]

    def test_ordered_by_updated_desc(self, client, db, candidate_headers, resume):
        base = datetime.now(UTC).replace(tzinfo=None)
        _backdate(db, resume.id, base - timedelta(hours=2))

        newer = _create_via_api(client, candidate_headers, title="新加的简历")
        _backdate(db, newer["id"], base - timedelta(hours=1))

        listed = client.get(URL, headers=candidate_headers).json()
        assert [item["id"] for item in listed] == [newer["id"], resume.id]

        # 改回较早那份 → 它的 updated_at 前进到现在，应升到最前
        client.put(
            f"{URL}/{resume.id}", json={"title": "改过的标题"}, headers=candidate_headers
        )

        listed = client.get(URL, headers=candidate_headers).json()
        assert [item["id"] for item in listed] == [resume.id, newer["id"]]


# ==================== 详情与更新（§7.3）====================


class TestDetailAndUpdateEndpoint:
    def test_get_own_ok(self, client, candidate_headers, resume):
        body = client.get(f"{URL}/{resume.id}", headers=candidate_headers).json()
        assert body["id"] == resume.id
        assert body["title"] == resume.title

    def test_get_missing_404(self, client, candidate_headers):
        assert client.get(f"{URL}/999999", headers=candidate_headers).status_code == 404

    def test_get_other_candidates_403(
        self, client, candidate_headers, other_candidate_headers, resume
    ):
        """资源存在但无权访问 → 403（沿用 ensure_resource_visible 的语义）。"""
        resp = client.get(f"{URL}/{resume.id}", headers=other_candidate_headers)
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_update_partial_title_only(self, client, candidate_headers, resume):
        body = client.put(
            f"{URL}/{resume.id}", json={"title": "新标题"}, headers=candidate_headers
        ).json()

        assert body["title"] == "新标题"
        assert body["content"] == resume.content  # 未提供的字段保持不变

    def test_update_content_over_limit_422(self, client, candidate_headers, resume):
        limit = get_settings().resume_content_max_length
        resp = client.put(
            f"{URL}/{resume.id}",
            json={"content": "正" * (limit + 1)},
            headers=candidate_headers,
        )
        assert resp.status_code == 422

    def test_update_other_candidates_403(
        self, client, candidate_headers, other_candidate_headers, resume
    ):
        resp = client.put(
            f"{URL}/{resume.id}", json={"title": "想改别人的"}, headers=other_candidate_headers
        )
        assert resp.status_code == 403


# ==================== 删除（§7.4）====================


class TestDeleteEndpoint:
    def test_delete_unreferenced_204(self, client, db, candidate_headers, resume):
        resume_id = resume.id  # 先取出 id：_fresh 会让实例过期，而行随后已不存在

        resp = client.delete(f"{URL}/{resume_id}", headers=candidate_headers)
        assert resp.status_code == 204

        _fresh(db)
        assert repository.get_by_id(db, resume_id) is None

    def test_delete_other_candidates_403(
        self, client, candidate_headers, other_candidate_headers, resume
    ):
        resp = client.delete(f"{URL}/{resume.id}", headers=other_candidate_headers)
        assert resp.status_code == 403

    def test_delete_missing_404(self, client, candidate_headers):
        assert client.delete(f"{URL}/999999", headers=candidate_headers).status_code == 404
