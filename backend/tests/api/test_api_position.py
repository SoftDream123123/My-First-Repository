"""API 接口测试 —— 模块 3/9：position（岗位）。

覆盖 5 个 method-route：
    POST   /api/positions
    GET    /api/positions
    GET    /api/positions/{position_id}
    PUT    /api/positions/{position_id}
    DELETE /api/positions/{position_id}

契约来源：
    docs/superpowers/specs/2026-09-15-module-02-position-plan.md §4 / §6
    docs/apis/API接口文档.md §6.1–§6.5

岗位是全项目的**隔离基座**：题目与面试都挂在它下面，它的可见性判据（`created_by`）
是后续所有 HR 侧数据隔离的样板。因此这里的隔离用例写得比别处更细。

补齐的空白：`PUT` / `DELETE` 对不存在 id 的 404、`name` 长度边界、
`keyword` 的空串与无命中。
"""

import pytest


def _create(client, headers, name="后端工程师", jd="负责后端开发与维护。", dims=None):
    """建岗位的薄封装，返回原始 Response 以便调用方各自断言。"""
    return client.post(
        "/api/positions",
        json={
            "name": name,
            "jd": jd,
            "evaluation_dimensions": dims if dims is not None else ["沟通能力", "专业能力"],
        },
        headers=headers,
    )


# ===========================================================================
# 6.1 创建岗位
# ===========================================================================


def test_create_position_returns_201_with_all_fields(client, hr_headers):
    resp = _create(client, hr_headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "后端工程师"
    assert body["jd"] == "负责后端开发与维护。"
    assert body["evaluation_dimensions"] == ["沟通能力", "专业能力"]
    assert isinstance(body["created_by"], int)
    assert "created_at" in body


def test_create_position_requires_hr_or_admin(client, candidate_headers):
    """候选人不能建岗位（403），且守卫先于请求体校验。"""
    resp = _create(client, candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_create_position_without_token_is_401(client):
    resp = _create(client, {})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "dims",
    [
        [],  # 一个都没有
        [""],  # 空串
        ["  "],  # 只有空白
        ["维度"] * 11,  # 超过 10 个
        ["x" * 51],  # 单个超过 50 字符
    ],
)
def test_create_position_rejects_bad_dimensions(client, hr_headers, dims):
    """维度列表是**多维度评分与出题的基准**，脏值必须挡在入口。

    `["维度"] * 11` 同时也在测「去重前还是去重后计数」—— 11 个相同维度
    应当因为超限被拒，而不是被去重成 1 个后放行。
    """
    resp = _create(client, hr_headers, dims=dims)

    assert resp.status_code == 400, f"{dims} -> {resp.status_code} {resp.text}"
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_create_position_rejects_duplicate_dimensions_case_insensitively(client, hr_headers):
    """「去重规则」是指**判定重复**，不是静默去重：重复了要 400 并指出是哪一项。

    计划书 §3.3 原文：「去重 | strip 后**不区分大小写**比较 | **400**，`detail` 含重复项」。
    也就是说 `"沟通能力"` 与 `" 沟通能力 "` 视为重复，`"Communication"` 与
    `"communication"` 视为重复 —— 命中任何一种都拒绝，而不是悄悄合并成一个。
    静默去重会掩盖前端数据错误，这里选择报错。
    """
    resp = _create(
        client, hr_headers, dims=["沟通能力", " 沟通能力 ", "Communication", "communication"]
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "重复" in resp.text


def test_create_position_keeps_original_casing_and_strips(client, hr_headers):
    """不重复时，存储的是 **strip 后、保留原始大小写** 的写法。"""
    resp = _create(client, hr_headers, dims=["  Communication  ", "逻辑思维"])

    assert resp.status_code == 201
    assert resp.json()["evaluation_dimensions"] == ["Communication", "逻辑思维"]


@pytest.mark.parametrize("name,jd", [("", "正常 JD"), ("n" * 101, "正常 JD")])
def test_create_position_rejects_bad_name(client, hr_headers, name, jd):
    resp = _create(client, hr_headers, name=name, jd=jd)

    assert resp.status_code == 400, f"{name!r} -> {resp.status_code}"


def test_create_position_accepts_whitespace_only_name(client, hr_headers):
    """⚠️ 记录实际行为（与别的模块不一致，见测试报告「发现的问题」）：

    `name` 只受 Pydantic 的 `min_length=1` 约束，**没有 strip 后非空校验**，
    因此 `"   "` 会被接受。而简历的 `title` / 练习的维度都是「strip 后非空」，
    同一项目里两种口径并存。

    这不是本文件要修的事（改行为属于产品变更），先把事实钉下来：
    哪天统一了口径，这条会红，正好提醒同步修改。
    """
    resp = _create(client, hr_headers, name="   ", jd="正常 JD")

    assert resp.status_code == 201
    assert resp.json()["name"].strip() == "", "存进去的确实是个空白名字"


def test_create_position_accepts_name_at_the_100_char_boundary(client, hr_headers):
    """⚠️ 补空白：100 字符是**合法**的（约束是 1–100，不是 1–99）。"""
    resp = _create(client, hr_headers, name="n" * 100)

    assert resp.status_code == 201
    assert len(resp.json()["name"]) == 100


def test_create_position_rejects_jd_over_10000_chars(client, hr_headers):
    resp = _create(client, hr_headers, jd="j" * 10001)

    assert resp.status_code == 400


def test_same_owner_cannot_reuse_position_name(client, hr_headers, position):
    """同一 HR 下岗位名唯一 → 409。"""
    resp = _create(client, hr_headers, name=position.name)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert "已存在" in resp.json()["message"]


def test_different_owners_may_reuse_the_same_position_name(client, hr_headers, other_hr_headers, position):
    """唯一键是 `(created_by, name)` —— 不同 HR 可以各自维护同名岗位。"""
    resp = _create(client, other_hr_headers, name=position.name)

    assert resp.status_code == 201


# ===========================================================================
# 6.2 岗位列表
# ===========================================================================


def test_list_positions_returns_only_own_as_hr(client, hr_headers, position, other_position):
    resp = client.get("/api/positions", headers=hr_headers)

    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids == [position.id], "只应看到自己创建的岗位"
    assert other_position.id not in ids


def test_list_positions_as_admin_sees_everyone(client, admin_headers, position, other_position):
    resp = client.get("/api/positions", headers=admin_headers)

    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {position.id, other_position.id} <= ids


def test_list_positions_is_ordered_by_id_ascending(client, hr_headers, position, db, hr_user):
    from app.position import service as position_service
    from app.position.schemas import PositionCreate

    later = position_service.create_position(
        db, hr_user, PositionCreate(name="第二岗位", jd="JD", evaluation_dimensions=["专业能力"])
    )

    resp = client.get("/api/positions", headers=hr_headers)

    ids = [p["id"] for p in resp.json()]
    assert ids == sorted(ids)
    assert ids == [position.id, later.id]


def test_list_positions_keyword_filters_by_name(client, hr_headers, position, other_position):
    hit = client.get("/api/positions?keyword=后端", headers=hr_headers)
    miss = client.get("/api/positions?keyword=前端", headers=hr_headers)

    assert [p["id"] for p in hit.json()] == [position.id]
    assert miss.json() == [], "他人员工不参与匹配，且无命中是空数组不是 404"


def test_list_positions_with_empty_keyword_returns_all(client, hr_headers, position):
    """空串 keyword 等同于「不筛选」（实现里走 `if keyword:` 的真值判断）。"""
    resp = client.get("/api/positions?keyword=", headers=hr_headers)

    assert resp.status_code == 200
    assert [p["id"] for p in resp.json()] == [position.id]


def test_list_positions_with_whitespace_keyword_is_not_treated_as_no_filter(client, hr_headers):
    """⚠️ 记录实际行为：纯空白 keyword **会被当成真条件**（`LIKE '%   %'`），
    结果是空列表，而不是「不筛选」 —— 因为 `bool("   ")` 为真。

    对前端的要求很具体：**不筛选时不要传 `keyword`，而不是传空串/空白**。
    传空串 `""` 反而等价于不筛选（见上一条），空白则不是，两者行为不同。
    """
    resp = client.get("/api/positions?keyword=%20%20%20", headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_positions_without_match_returns_empty_array(client, hr_headers, position):
    """无命中是 `[]`，不是 404 也不是 null。"""
    resp = client.get("/api/positions?keyword=不存在的岗位名", headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_positions_without_token_is_401(client):
    resp = client.get("/api/positions")

    assert resp.status_code == 401


# ===========================================================================
# 6.3 岗位详情
# ===========================================================================


def test_get_position_returns_200_for_owner(client, hr_headers, position):
    resp = client.get(f"/api/positions/{position.id}", headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json()["id"] == position.id


def test_get_other_owners_position_is_403(client, hr_headers, other_position):
    """资源存在但无权访问 → 403（有意暴露存在性），不是 404。"""
    resp = client.get(f"/api/positions/{other_position.id}", headers=hr_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_get_nonexistent_position_is_404(client, hr_headers):
    resp = client.get("/api/positions/424242", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ===========================================================================
# 6.4 更新岗位
# ===========================================================================


def test_update_position_replaces_dimensions_instead_of_appending(client, hr_headers, position):
    """`PUT` 是**全量替换** —— 维度列表不会被追加，而是整段换掉。"""
    resp = client.put(
        f"/api/positions/{position.id}",
        json={"name": position.name, "jd": "改过的 JD", "evaluation_dimensions": ["逻辑思维"]},
        headers=hr_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["jd"] == "改过的 JD"
    assert body["evaluation_dimensions"] == ["逻辑思维"], "旧的两个维度必须消失"


def test_update_position_to_its_own_name_is_allowed(client, hr_headers, position):
    """改回自己原名不应撞唯一键（先查重再排除自己）。"""
    resp = client.put(
        f"/api/positions/{position.id}",
        json={"name": position.name, "jd": "同一个名字", "evaluation_dimensions": ["专业能力"]},
        headers=hr_headers,
    )

    assert resp.status_code == 200


def test_update_position_to_another_owners_name_is_allowed(client, hr_headers, position, other_position):
    """撞车只在**同一创建人**范围内判定 —— 别人有同名岗位不影响我。"""
    resp = client.put(
        f"/api/positions/{position.id}",
        json={"name": other_position.name, "jd": "JD", "evaluation_dimensions": ["专业能力"]},
        headers=hr_headers,
    )

    assert resp.status_code == 200


def test_update_position_name_collision_within_own_scope_is_409(client, hr_headers, position, db, hr_user):
    from app.position import service as position_service
    from app.position.schemas import PositionCreate

    second = position_service.create_position(
        db, hr_user, PositionCreate(name="另一岗位", jd="JD", evaluation_dimensions=["专业能力"])
    )

    resp = client.put(
        f"/api/positions/{second.id}",
        json={"name": position.name, "jd": "JD", "evaluation_dimensions": ["专业能力"]},
        headers=hr_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_update_other_owners_position_is_403(client, hr_headers, other_position):
    resp = client.put(
        f"/api/positions/{other_position.id}",
        json={"name": "改名", "jd": "JD", "evaluation_dimensions": ["专业能力"]},
        headers=hr_headers,
    )

    assert resp.status_code == 403


def test_update_nonexistent_position_is_404(client, hr_headers):
    """⚠️ 补空白：`PUT` 对不存在 id 此前没有用例。"""
    resp = client.put(
        "/api/positions/424242",
        json={"name": "名字", "jd": "JD", "evaluation_dimensions": ["专业能力"]},
        headers=hr_headers,
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ===========================================================================
# 6.5 删除岗位
# ===========================================================================


def test_delete_position_returns_204_with_empty_body(client, hr_headers, position):
    resp = client.delete(f"/api/positions/{position.id}", headers=hr_headers)

    assert resp.status_code == 204
    assert resp.content == b"", "204 必须没有响应体"
    assert client.get(f"/api/positions/{position.id}", headers=hr_headers).status_code == 404


def test_delete_position_referenced_by_question_is_409(client, hr_headers, position, practice_questions):
    """岗位被题目引用 → 拒绝（外键 RESTRICT → 业务错误，不是 500）。"""
    resp = client.delete(f"/api/positions/{position.id}", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert "无法删除" in resp.json()["message"]


def test_delete_position_referenced_by_interview_is_409(client, hr_headers, position):
    """⚠️ 岗位**只被面试引用**（底下没有题目）时同样要 409。

    这条与上一条走的是**两条不同的外键**（`question.position_id` 与
    `interview.position_id`）。只测其中一条，另一条漏了也发现不了。
    """
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    )
    assert created.status_code == 201

    resp = client.delete(f"/api/positions/{position.id}", headers=hr_headers)

    assert resp.status_code == 409
    assert "无法删除" in resp.json()["message"]


def test_delete_other_owners_position_is_403(client, hr_headers, other_position):
    resp = client.delete(f"/api/positions/{other_position.id}", headers=hr_headers)

    assert resp.status_code == 403


def test_delete_nonexistent_position_is_404(client, hr_headers):
    """⚠️ 补空白：`DELETE` 对不存在 id 此前没有用例。"""
    resp = client.delete("/api/positions/424242", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_deleted_position_frees_its_name_for_reuse(client, hr_headers, position):
    """删掉后同名可再建 —— 唯一键是数据库层的，删干净就该能重用。"""
    assert client.delete(f"/api/positions/{position.id}", headers=hr_headers).status_code == 204

    assert _create(client, hr_headers, name=position.name).status_code == 201
