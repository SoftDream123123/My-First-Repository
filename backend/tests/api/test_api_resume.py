"""API 接口测试 —— 模块 5/9：resume（简历，候选人侧）。

覆盖 5 个 method-route（全部要求 `candidate` 角色）：
    POST   /api/candidate/resumes
    GET    /api/candidate/resumes
    GET    /api/candidate/resumes/{resume_id}
    PUT    /api/candidate/resumes/{resume_id}
    DELETE /api/candidate/resumes/{resume_id}

契约来源：
    docs/superpowers/specs/2026-09-21-module-17-resume-plan.md §4 / §6
    docs/apis/API接口文档.md §11.1–§11.5

本模块有**两个全项目独一份**的地方，用例专门盯着：
    1. 正文超长是 **422**，而别处的参数校验都是 400；
    2. `PUT` 虽然是 PUT，语义却是**部分更新**（漏传 = 不变，传 null 也 = 不变）。
"""

import pytest

from app.core.config import get_settings
from tests.upload_helpers import docx_bytes

RESUME_BODY = "五年 Python 后端开发经验，主导过服务拆分与性能优化。"


def _create(client, headers, **overrides):
    payload = {"title": "张三-后端开发", "content": RESUME_BODY}
    payload.update(overrides)
    return client.post("/api/candidate/resumes", json=payload, headers=headers)


# ===========================================================================
# 11.1 新建简历
# ===========================================================================


def test_create_resume_returns_201_without_created_by(client, candidate_headers):
    resp = _create(
        client,
        candidate_headers,
        candidate_name="张三",
        candidate_contact="zhangsan@example.com",
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "张三-后端开发"
    assert body["content"] == RESUME_BODY
    assert body["candidate_name"] == "张三"
    assert "created_by" not in body, "候选人不需要知道自己的 user id"
    assert "created_at" in body and "updated_at" in body


def test_create_resume_ignores_client_supplied_created_by(client, candidate_headers, other_candidate):
    """请求体里的 `created_by` 只是普通未知字段，不能决定归属。"""
    resp = _create(client, candidate_headers, created_by=other_candidate.id)

    assert resp.status_code == 201
    # 用本人身份读得到，且列表里只有这一份
    assert [r["id"] for r in client.get("/api/candidate/resumes", headers=candidate_headers).json()] == [
        resp.json()["id"]
    ]


def test_create_resume_requires_candidate_role(client, hr_headers, admin_headers):
    assert _create(client, hr_headers).status_code == 403
    assert _create(client, admin_headers).status_code == 403


def test_create_resume_without_token_is_401(client):
    resp = _create(client, {})

    assert resp.status_code == 401


@pytest.mark.parametrize("title", ["", "t" * 101])
def test_create_resume_rejects_bad_title(client, candidate_headers, title):
    resp = _create(client, candidate_headers, title=title)

    assert resp.status_code == 400, f"title={title!r} -> {resp.status_code}"


def test_create_resume_accepts_title_at_100_char_boundary(client, candidate_headers):
    resp = _create(client, candidate_headers, title="t" * 100)

    assert resp.status_code == 201


@pytest.mark.parametrize("content", ["", "   "])
def test_create_resume_rejects_blank_content(client, candidate_headers, content):
    resp = _create(client, candidate_headers, content=content)

    assert resp.status_code == 400


def test_create_resume_content_at_20000_chars_is_accepted(client, candidate_headers):
    """20000 是**合法**上限（限制是「不能超过」）。"""
    resp = _create(client, candidate_headers, content="正" * 20000)

    assert resp.status_code == 201


def test_create_resume_content_over_limit_is_422_not_400(client, candidate_headers):
    """⚠️ 全项目**唯一一处 422**。

    该校验刻意绕开 Pydantic —— 若交给 Pydantic 的 `max_length`，会被 `main.py`
    的全局处理器统一改写为 400，与 PRD §7 要求的 422 不符。这条用例同时钉住
    「是 422」与「code 仍是 VALIDATION_ERROR 且 message 可读」。
    """
    resp = _create(client, candidate_headers, content="正" * 20001)

    assert resp.status_code == 422, f"应为 422，实际 {resp.status_code}"
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "20000" in body["message"]


def test_create_resume_rejects_overlong_candidate_fields(client, candidate_headers):
    assert _create(client, candidate_headers, candidate_name="n" * 101).status_code == 400
    assert _create(client, candidate_headers, candidate_contact="c" * 201).status_code == 400


# ===========================================================================
# 11.2 我的简历列表
# ===========================================================================


def test_list_resumes_includes_full_content(client, candidate_headers, resume):
    """列表**下发 content 全文** —— 候选人的简历就是一份文本，列表页要显示摘要。"""
    resp = client.get("/api/candidate/resumes", headers=candidate_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body] == [resume.id]
    assert body[0]["content"] == resume.content
    assert "created_by" not in body[0]


def test_list_resumes_is_empty_array_when_none(client, candidate_headers):
    resp = client.get("/api/candidate/resumes", headers=candidate_headers)

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_resumes_ordered_by_updated_at_desc(client, candidate_headers, db):
    """按 `updated_at` **降序**，而不是按 id。

    这里同样要先把「先建的」回退到过去 —— 否则两份落在同一秒，
    排序靠 `id desc` 兜底，用例会「碰巧通过」却完全没验证 `updated_at`。
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    older = _create(client, candidate_headers, title="先建的").json()
    newer = _create(client, candidate_headers, title="后建的").json()

    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    db.execute(
        text("UPDATE `resume` SET updated_at = :w WHERE id = :i"),
        {"w": past, "i": older["id"]},
    )
    db.commit()

    ids = [r["id"] for r in client.get("/api/candidate/resumes", headers=candidate_headers).json()]

    assert ids == [newer["id"], older["id"]], "最近更新的在前"


def test_list_resumes_updated_order_changes_after_edit(client, candidate_headers, db):
    """改过的那一份应当冒到最前面 —— 这正是 `updated_at` 的用途。

    ⚠️ 必须先把两份**都回退到过去**（且让待编辑的那份更旧），否则用例是空的：
    `DATETIME` 只精确到**秒**，两份在同一秒内创建、编辑又落在同一秒时，
    排序会退到 `id desc` 兜底 —— 那时「编辑把它顶上来」根本体现不出来，
    用例只是碰巧通过。回退之后 `first` 的 `updated_at` 才真正领先。

    按项目惯例用 SQL 回退时间，**不 sleep**（sleep 赌时间窗口是竞态的温床）。
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    first = _create(client, candidate_headers, title="第一份").json()
    second = _create(client, candidate_headers, title="第二份").json()

    now = datetime.now(UTC).replace(tzinfo=None)
    for resume_id, when in ((first["id"], now - timedelta(hours=3)), (second["id"], now - timedelta(hours=1))):
        db.execute(
            text("UPDATE `resume` SET created_at = :w, updated_at = :w WHERE id = :i"),
            {"w": when, "i": resume_id},
        )
    db.commit()

    before = [
        r["id"] for r in client.get("/api/candidate/resumes", headers=candidate_headers).json()
    ]
    assert before == [second["id"], first["id"]], "前置：被回退的那份排在后面"

    client.put(
        f"/api/candidate/resumes/{first['id']}",
        json={"title": "第一份（改过）"},
        headers=candidate_headers,
    )

    after = [
        r["id"] for r in client.get("/api/candidate/resumes", headers=candidate_headers).json()
    ]
    assert after == [first["id"], second["id"]], "编辑后它应当排到最前"


def test_list_resumes_isolated_between_candidates(client, candidate_headers, other_candidate_headers, resume, other_resume):
    mine = [r["id"] for r in client.get("/api/candidate/resumes", headers=candidate_headers).json()]
    theirs = [r["id"] for r in client.get("/api/candidate/resumes", headers=other_candidate_headers).json()]

    assert mine == [resume.id]
    assert theirs == [other_resume.id]


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_list_resumes_rejects_out_of_range_limit(client, candidate_headers, limit):
    """`limit` 是 `ge=1, le=200`：越界**明确报错**，不静默截断。"""
    resp = client.get(f"/api/candidate/resumes?limit={limit}", headers=candidate_headers)

    assert resp.status_code == 400, f"limit={limit} -> {resp.status_code}"


def test_list_resumes_accepts_limit_at_boundaries(client, candidate_headers, resume):
    assert client.get("/api/candidate/resumes?limit=1", headers=candidate_headers).status_code == 200
    assert client.get("/api/candidate/resumes?limit=200", headers=candidate_headers).status_code == 200


# ===========================================================================
# 11.3 简历详情
# ===========================================================================


def test_get_own_resume_returns_200(client, candidate_headers, resume):
    resp = client.get(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == resume.id
    assert body["title"] == resume.title
    assert body["content"] == resume.content
    assert body["updated_at"] >= body["created_at"], "刚建出来时两者应相等或接近"


def test_get_other_candidates_resume_is_403(client, candidate_headers, other_resume):
    resp = client.get(f"/api/candidate/resumes/{other_resume.id}", headers=candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_get_nonexistent_resume_is_404(client, candidate_headers):
    resp = client.get("/api/candidate/resumes/424242", headers=candidate_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ===========================================================================
# 11.4 更新我的简历
# ===========================================================================


def test_update_resume_is_partial(client, candidate_headers, resume):
    """⚠️ 是 `PUT` 但语义是**部分更新**：只改标题，正文原样保留。"""
    resp = client.put(
        f"/api/candidate/resumes/{resume.id}",
        json={"title": "改过的标题"},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "改过的标题"
    assert body["content"] == resume.content, "没传的字段必须保持不变"


def test_update_resume_with_explicit_null_also_keeps_the_value(client, candidate_headers, resume):
    """传显式 `null` **也表示「不修改」** —— 因此没有「清空姓名」这个操作。

    对简历这种整块文本，清空与不填在展示上等价，所以不值得引入第二种空值语义。
    """
    resp = client.put(
        f"/api/candidate/resumes/{resume.id}",
        json={"candidate_name": None, "title": "只改标题"},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["candidate_name"] == resume.candidate_name, "没被清空"


def test_update_resume_refreshes_updated_at(client, candidate_headers, resume):
    """`updated_at` 必须真的前进 —— HR 靠它判断手上这份是不是最新的。"""
    before = client.get(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers).json()

    after = client.put(
        f"/api/candidate/resumes/{resume.id}",
        json={"content": RESUME_BODY + "（补充了一段）"},
        headers=candidate_headers,
    ).json()

    assert after["updated_at"] >= before["updated_at"]
    assert after["content"].endswith("（补充了一段）")


def test_update_resume_content_over_limit_is_422(client, candidate_headers, resume):
    resp = client.put(
        f"/api/candidate/resumes/{resume.id}",
        json={"content": "正" * 20001},
        headers=candidate_headers,
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_update_resume_rejects_blank_title(client, candidate_headers, resume):
    """`title` 在更新模型里是 `min_length=1` —— 显式传空串是 400，不是「清空」。"""
    resp = client.put(
        f"/api/candidate/resumes/{resume.id}", json={"title": ""}, headers=candidate_headers
    )

    assert resp.status_code == 400


def test_update_other_candidates_resume_is_403(client, candidate_headers, other_resume):
    resp = client.put(
        f"/api/candidate/resumes/{other_resume.id}",
        json={"title": "想改别人的"},
        headers=candidate_headers,
    )

    assert resp.status_code == 403


def test_update_nonexistent_resume_is_404(client, candidate_headers):
    """⚠️ 补空白：`PUT` 对不存在 id 此前没有用例。"""
    resp = client.put(
        "/api/candidate/resumes/424242", json={"title": "不存在"}, headers=candidate_headers
    )

    assert resp.status_code == 404


# ===========================================================================
# 11.5 删除我的简历
# ===========================================================================


def test_delete_resume_returns_204_with_empty_body(client, candidate_headers, resume):
    resp = client.delete(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers)

    assert resp.status_code == 204
    assert resp.content == b""
    assert client.get("/api/candidate/resumes", headers=candidate_headers).json() == []


def test_delete_resume_referenced_by_interview_is_409(
    client, candidate_headers, linked_interview, resume
):
    """简历已被某场面试关联 → 409，且**简历仍在**（事务整体回滚）。"""
    resp = client.delete(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert "无法删除" in resp.json()["message"]

    still_there = client.get(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers)
    assert still_there.status_code == 200, "被拒后简历必须原样留着"


def test_delete_resume_referenced_by_practice_is_409(
    client, candidate_headers, resume, practice_questions
):
    """练习侧是**另一条外键**（`practice_session.resume_id`）。

    只测面试那条路径，练习这条漏了也发现不了 —— 反过来也一样。
    """
    started = client.post(
        "/api/practice/sessions", json={"size": 4, "resume_id": resume.id}, headers=candidate_headers
    )
    assert started.status_code == 201, started.text

    resp = client.delete(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers)

    assert resp.status_code == 409
    assert "无法删除" in resp.json()["message"]


def test_delete_resume_works_after_unlinking(client, candidate_headers, linked_interview, resume):
    """解除关联之后就能删 —— 409 不是死结，前端要给出「去解除关联」的入口。"""
    unlinked = client.put(
        f"/api/candidate/interviews/{linked_interview['interview_id']}/resume",
        json={"resume_id": None},
        headers=candidate_headers,
    )
    assert unlinked.status_code == 200

    assert client.delete(f"/api/candidate/resumes/{resume.id}", headers=candidate_headers).status_code == 204


def test_delete_other_candidates_resume_is_403(client, candidate_headers, other_resume):
    resp = client.delete(f"/api/candidate/resumes/{other_resume.id}", headers=candidate_headers)

    assert resp.status_code == 403


def test_delete_nonexistent_resume_is_404(client, candidate_headers):
    resp = client.delete("/api/candidate/resumes/424242", headers=candidate_headers)

    assert resp.status_code == 404


def test_resume_endpoints_reject_hr_and_admin(client, hr_headers, admin_headers, resume):
    """候选人侧守卫精确匹配：HR 与 admin 一律 403（admin 也不通）。"""
    for headers in (hr_headers, admin_headers):
        assert client.get("/api/candidate/resumes", headers=headers).status_code == 403
        assert client.get(f"/api/candidate/resumes/{resume.id}", headers=headers).status_code == 403
        assert (
            client.put(
                f"/api/candidate/resumes/{resume.id}", json={"title": "x"}, headers=headers
            ).status_code
            == 403
        )
        assert client.delete(f"/api/candidate/resumes/{resume.id}", headers=headers).status_code == 403


# ===========================================================================
# 11.6 上传解析（MVP-4，PRD §4.10）
# ===========================================================================

PARSE_PATH = "/api/candidate/resumes/parse"


def test_parse_upload_returns_text(client, candidate_headers):
    resp = client.post(
        PARSE_PATH,
        files={"file": ("简历.docx", docx_bytes(["张三", "五年后端经验"]), "application/octet-stream")},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "张三" in content and "五年后端经验" in content


def test_parse_upload_does_not_create_a_resume(client, candidate_headers):
    """PRD §5.2 的「客户端点不落库」—— 直接断言库内简历数不变。"""
    before = len(client.get("/api/candidate/resumes", headers=candidate_headers).json())

    resp = client.post(
        PARSE_PATH,
        files={"file": ("简历.docx", docx_bytes(["正文"]), "application/octet-stream")},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    after = client.get("/api/candidate/resumes", headers=candidate_headers).json()
    assert len(after) == before


def test_parse_upload_extracts_table_text(client, candidate_headers):
    """表格里的话必须被抠出来 —— 简历常把经历做成表格。"""
    resp = client.post(
        PARSE_PATH,
        files={
            "file": (
                "简历.docx",
                docx_bytes([[["某大学", "计算机"], ["某公司", "后端"]]]),
                "application/octet-stream",
            )
        },
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    assert "某大学" in resp.json()["content"]


def test_parse_upload_rejects_unsupported_extension(client, candidate_headers):
    resp = client.post(
        PARSE_PATH,
        files={"file": ("简历.doc", b"anything", "application/octet-stream")},
        headers=candidate_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_parse_upload_rejects_oversize_file(client, candidate_headers):
    limit = get_settings().resume_upload_max_bytes
    resp = client.post(
        PARSE_PATH,
        files={"file": ("简历.pdf", b"%PDF-" + b"0" * limit, "application/pdf")},
        headers=candidate_headers,
    )

    assert resp.status_code == 400
    assert "5 MB" in resp.json()["message"]


def test_parse_upload_requires_file_field(client, candidate_headers):
    assert client.post(PARSE_PATH, headers=candidate_headers).status_code == 400


def test_parse_upload_rejects_hr_and_admin(client, hr_headers, admin_headers):
    """候选人侧守卫精确匹配：HR 与 admin 一律 403（admin 也不通）。"""
    for headers in (hr_headers, admin_headers):
        resp = client.post(
            PARSE_PATH,
            files={"file": ("简历.docx", docx_bytes(["x"]), "application/octet-stream")},
            headers=headers,
        )
        assert resp.status_code == 403


def test_parse_upload_requires_authentication(client):
    resp = client.post(
        PARSE_PATH,
        files={"file": ("简历.docx", docx_bytes(["x"]), "application/octet-stream")},
    )

    assert resp.status_code == 401
