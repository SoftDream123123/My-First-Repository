"""API 接口测试 —— 模块 8/9：候选人端（在线作答）。

覆盖 7 个 method-route（`GET .../feedback` 属模块 7）：
    GET  /api/candidate/positions                          刷题岗位筛选项
    POST /api/candidate/invitations/{code}/accept          凭邀请码激活并绑定
    GET  /api/candidate/interviews                         我参与的面试
    GET  /api/candidate/interviews/{interview_id}          面试详情（候选人视图）
    POST /api/candidate/interviews/{interview_id}/answers  保存 / 更新我的作答
    POST /api/candidate/interviews/{interview_id}/submit   交卷
    PUT  /api/candidate/interviews/{interview_id}/resume   关联 / 解除关联简历

契约来源：
    docs/superpowers/specs/2026-09-20-module-12-interview-invitation-plan.md §4 / §5
    docs/superpowers/specs/2026-09-21-module-19-interview-plan.md §4 / §5
    docs/apis/API接口文档.md §10.1–§10.7

⚠️ 本文件的断言目标是**候选人视图的字段边界**，不是值：
    题目的键集合只有 5 个，`match_reason` / `score` / `comment` / `created_by`
    在响应里**结构上不存在**。「前端不渲染」不算脱敏 —— 那是把数据发给了浏览器。
"""

import pytest

CANDIDATE_QUESTION_KEYS = {
    "interview_question_id",
    "seq",
    "content",
    "dimension",
    "my_answer",
}


# ===========================================================================
# 10.1 刷题岗位筛选项
# ===========================================================================


def test_candidate_positions_lists_only_positions_with_questions(client, candidate_headers, practice_questions, position):
    resp = client.get("/api/candidate/positions", headers=candidate_headers)

    assert resp.status_code == 200
    rows = resp.json()
    row = next(r for r in rows if r["id"] == position.id)
    assert row["name"] == position.name
    assert row["question_count"] == len(practice_questions)


def test_candidate_positions_omits_jd_and_owner(client, candidate_headers, practice_questions):
    """只下发筛选标识 —— 岗位 JD 属 HR 侧内容，候选人不该看到。"""
    rows = client.get("/api/candidate/positions", headers=candidate_headers).json()

    assert rows, "前置应有岗位"
    assert set(rows[0]) == {"id", "name", "question_count"}


def test_candidate_positions_excludes_positions_without_questions(client, candidate_headers, position):
    """没题的岗位不该出现在筛选项里（否则选了也刷不出题）。"""
    assert client.get("/api/candidate/positions", headers=candidate_headers).json() == []


def test_candidate_positions_is_ordered_by_id(client, candidate_headers, practice_questions, db, hr_user):
    from app.position import service as position_service
    from app.position.schemas import PositionCreate
    from app.question import repository

    later = position_service.create_position(
        db, hr_user, PositionCreate(name="第二个岗位", jd="JD", evaluation_dimensions=["专业能力"])
    )
    repository.create(
        db,
        position_id=later.id,
        category="通用",
        dimension="专业能力",
        content="第二个岗位的一道题的题干",
        difficulty="medium",
        tags=[],
        source="bank",
        created_by=hr_user.id,
    )
    db.commit()

    ids = [r["id"] for r in client.get("/api/candidate/positions", headers=candidate_headers).json()]

    assert ids == sorted(ids)


def test_candidate_positions_rejects_hr_side(client, hr_headers, admin_headers, practice_questions):
    assert client.get("/api/candidate/positions", headers=hr_headers).status_code == 403
    assert client.get("/api/candidate/positions", headers=admin_headers).status_code == 403


# ===========================================================================
# 10.2 接受邀请码
# ===========================================================================


def _accept(client, headers, code, username="cand_test", password="cand12345678"):
    return client.post(
        f"/api/candidate/invitations/{code}/accept",
        json={"username": username, "password": password},
        headers=headers,
    )


def test_accept_binds_interview_and_returns_no_token(client, hr_headers, candidate_headers, position):
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    resp = _accept(client, candidate_headers, invitation["code"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["interview_id"] == interview["id"]
    assert set(body["interview"]) == {
        "id",
        "position_name",
        "candidate_name",
        "status",
        "question_count",
    }
    assert "token" not in body, "接受邀请不等于登录"


def test_accept_reuses_existing_candidate_account(client, hr_headers, candidate_headers, candidate_user, position):
    """已存在的 candidate 账号会被**复用**（候选人可能已有刷题账号，不该被迫换名）。"""
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    resp = _accept(client, candidate_headers, invitation["code"], username=candidate_user.username)

    assert resp.status_code == 200
    # 仍然只有这一个候选人账号在参与这场面试
    mine = client.get("/api/candidate/interviews", headers=candidate_headers).json()
    assert [m["id"] for m in mine] == [interview["id"]]


def test_accept_all_four_invalid_reasons_share_one_message(client, hr_headers, candidate_headers, position):
    """⚠️ 不存在 / 已撤销 / 已接受 / 已过期 —— **文案与状态码完全相同**。

    否则邀请码接口就成了「这个码是否存在」「是否已被别人用了」的探测器。
    """
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    unknown = _accept(client, candidate_headers, "no-such-code-at-all")

    revoked_code = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()
    client.delete(
        f"/api/interviews/{interview['id']}/invitations/{revoked_code['id']}", headers=hr_headers
    )
    revoked = _accept(client, candidate_headers, revoked_code["code"])

    assert unknown.status_code == revoked.status_code == 409
    assert unknown.text == revoked.text


def test_accept_twice_is_conflict(client, hr_headers, candidate_headers, accepted_interview):
    """重复接受同一邀请 → 409「你已接受过该面试的邀请」。"""
    resp = _accept(client, candidate_headers, accepted_interview["code"])

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_accept_rejects_hr_username_without_leaking_role(client, hr_headers, candidate_headers, hr_user, position):
    """用户名被 HR 占用 → 409「用户名已被占用」，且**邀请保持 pending**（无部分写入）。"""
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    resp = _accept(client, candidate_headers, invitation["code"], username=hr_user.username)

    assert resp.status_code == 409
    assert "占用" in resp.json()["message"]

    still_pending = client.get(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()[0]
    assert still_pending["status"] == "pending", "失败不能留下半成品"


def test_accept_short_password_is_400(client, hr_headers, candidate_headers, position):
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    resp = _accept(client, candidate_headers, invitation["code"], password="short")

    assert resp.status_code == 400


def test_accept_requires_a_logged_in_candidate_token(client, hr_headers, position):
    """⚠️ 记录**已知偏差 1**（后端与计划书不一致，尚未修复）。

    计划书描述的是「新人凭码**一步**激活」，但本端点挂的是
    `require_roles("candidate")` —— 调用者必须**已经是**登录中的候选人。
    新人没有账号、也就拿不到 token，因此这里只能返回 401。

    这条用例的作用是把现状钉住：哪天守卫改成公开端点，它会变红，提醒同步更新
    `docs/apis/API接口文档.md` §10.2 的偏差说明。
    """
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()
    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    anonymous = _accept(client, {}, invitation["code"], username="brand_new_person")

    assert anonymous.status_code == 401, "现状：新人无法凭码直接激活"
    assert anonymous.json()["code"] == "UNAUTHORIZED"


# ===========================================================================
# 10.3 我的面试列表
# ===========================================================================


def test_my_interviews_lists_only_accepted(client, hr_headers, candidate_headers, position, accepted_interview):
    """只列出**已接受**的面试：另发一张没接受的邀请，它不应出现。"""
    other = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "王五"},
        headers=hr_headers,
    ).json()
    client.post(f"/api/interviews/{other['id']}/invitations", headers=hr_headers)

    rows = client.get("/api/candidate/interviews", headers=candidate_headers).json()

    assert [r["id"] for r in rows] == [accepted_interview["interview_id"]]


def test_my_interviews_includes_resume_id(client, candidate_headers, linked_interview):
    """⚠️ `resume_id` 必须下发 —— 候选人要能看到自己关联了哪一份。

    「能写就必须能读」：没有它，候选人只能盲改关联，也判断不出「解除关联」该不该给。
    """
    rows = client.get("/api/candidate/interviews", headers=candidate_headers).json()

    row = next(r for r in rows if r["id"] == linked_interview["interview_id"])
    assert row["resume_id"] is not None


def test_my_interviews_resume_id_is_null_when_not_linked(client, candidate_headers, accepted_interview):
    rows = client.get("/api/candidate/interviews", headers=candidate_headers).json()

    assert rows[0]["resume_id"] is None


def test_my_interviews_rejects_hr_side(client, hr_headers, accepted_interview):
    assert client.get("/api/candidate/interviews", headers=hr_headers).status_code == 403


# ===========================================================================
# 10.4 面试详情（候选人视图）
# ===========================================================================


def test_candidate_detail_question_keys_are_exactly_five(client, candidate_headers, accepted_interview):
    """⚠️ 题目对象的键集合**恰好**是 5 个 —— 脱敏靠结构，不靠前端。

    多一个字段（比如 `match_reason`、`score`）这条就红。
    """
    detail = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    ).json()

    assert detail["questions"]
    for question in detail["questions"]:
        assert set(question) == CANDIDATE_QUESTION_KEYS, set(question)
        assert question["my_answer"] is None


def test_candidate_detail_never_leaks_hr_material(client, candidate_headers, accepted_interview):
    """在**原始响应文本**里搜 HR 侧的字段名与内容。"""
    resp = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    )

    for forbidden in ("match_reason", "comment", "created_by", "answer_source", "source_snapshot"):
        assert forbidden not in resp.text, f"泄漏了 {forbidden}"


def test_candidate_detail_does_not_expose_match_reason_after_matching(
    client, hr_headers, candidate_headers, linked_interview, match_pool, monkeypatch
):
    """补题之后，候选人视图**仍然**看不到 `match_reason`（那是 HR 的决策辅助）。"""
    from app.ai.base import MatchedQuestion

    class _Provider:
        def __getattr__(self, name):
            def _match(resume_text, position_name, jd, dims, candidates, count):
                return [
                    MatchedQuestion(question_id=c.question_id, reason="简历里提到过这段经历")
                    for c in candidates[:1]
                ]

            return _match

    monkeypatch.setattr("app.interview.service.get_provider", lambda: _Provider())
    matched = client.post(
        f"/api/interviews/{linked_interview['interview_id']}/questions/match",
        json={"count": 1},
        headers=hr_headers,
    )
    assert matched.status_code == 200 and matched.json()["added_count"] == 1

    resp = client.get(
        f"/api/candidate/interviews/{linked_interview['interview_id']}", headers=candidate_headers
    )

    assert "match_reason" not in resp.text
    assert "简历里提到过这段经历" not in resp.text


def test_candidate_detail_uses_snapshot_content(client, candidate_headers, accepted_interview, db, hr_headers):
    """候选人看到的题干来自**快照**（HR 改题库不影响正在进行的面试）。"""
    detail = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    ).json()
    contents_before = [q["content"] for q in detail["questions"]]

    again = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    ).json()

    assert [q["content"] for q in again["questions"]] == contents_before


def test_candidate_cannot_read_uninvited_interview(client, candidate_headers, hr_headers, position):
    """未被邀请的面试 → 403（不是 404：不泄露存在性）。"""
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.get(f"/api/candidate/interviews/{interview['id']}", headers=candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_candidate_cannot_read_other_candidates_interview(client, other_candidate_headers, accepted_interview):
    resp = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}",
        headers=other_candidate_headers,
    )

    assert resp.status_code == 403


def test_candidate_detail_nonexistent_is_404(client, candidate_headers):
    assert client.get("/api/candidate/interviews/424242", headers=candidate_headers).status_code == 404


# ===========================================================================
# 10.5 保存 / 更新我的作答
# ===========================================================================


def test_save_answer_returns_view_with_submitted_at(client, candidate_headers, accepted_interview):
    detail = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    ).json()
    iq_id = detail["questions"][0]["interview_question_id"]

    resp = client.post(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/answers",
        json={"interview_question_id": iq_id, "content": "我的作答"},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"interview_question_id", "content", "submitted_at"}
    assert body["content"] == "我的作答"
    assert body["submitted_at"] is None, "还没交卷"


def test_save_answer_updates_in_place(client, candidate_headers, accepted_interview):
    interview_id = accepted_interview["interview_id"]
    detail = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    iq_id = detail["questions"][0]["interview_question_id"]

    for text in ("第一次", "改过一次"):
        client.post(
            f"/api/candidate/interviews/{interview_id}/answers",
            json={"interview_question_id": iq_id, "content": text},
            headers=candidate_headers,
        )

    after = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    assert after["questions"][0]["my_answer"] == "改过一次"

    # 计数只在**列表项**上（详情不含 answered_count），所以计数要换个接口看
    row = next(
        r
        for r in client.get("/api/candidate/interviews", headers=candidate_headers).json()
        if r["id"] == interview_id
    )
    assert row["answered_count"] == 1, "更新而非新增"


def test_save_answer_rejects_foreign_question(client, candidate_headers, accepted_interview, hr_headers, position):
    other = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "王五"},
        headers=hr_headers,
    ).json()

    resp = client.post(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/answers",
        json={"interview_question_id": other["questions"][0]["interview_question_id"], "content": "x"},
        headers=candidate_headers,
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_save_answer_rejected_after_submit(client, candidate_headers, accepted_interview):
    interview_id = accepted_interview["interview_id"]
    detail = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    iq_id = detail["questions"][0]["interview_question_id"]
    client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers)

    resp = client.post(
        f"/api/candidate/interviews/{interview_id}/answers",
        json={"interview_question_id": iq_id, "content": "交卷后还想改"},
        headers=candidate_headers,
    )

    assert resp.status_code == 409
    assert "交卷" in resp.json()["message"]


# ===========================================================================
# 10.6 交卷
# ===========================================================================


def test_submit_returns_result_and_does_not_change_interview_status(
    client, candidate_headers, accepted_interview
):
    """⚠️ 交卷**不推进面试状态** —— 面试仍是 `ongoing`，等 HR 标记完成。"""
    resp = client.post(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/submit",
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"interview_id", "submitted_at", "answered_count"}
    assert body["submitted_at"] is not None

    after = client.get(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}", headers=candidate_headers
    ).json()
    assert after["submitted"] is True
    assert after["status"] == "ongoing", "交卷不推进面试状态"


def test_submit_is_idempotent_and_keeps_first_timestamp(client, candidate_headers, accepted_interview):
    """重复交卷返回 **200**，且 `submitted_at` 仍是**第一次**的值。"""
    interview_id = accepted_interview["interview_id"]

    first = client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers)
    second = client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["submitted_at"] == second.json()["submitted_at"], "不能被刷新"


def test_submit_counts_only_non_blank_answers(client, candidate_headers, accepted_interview):
    """空串作答算「提交过」但**不计入** `answered_count`。"""
    interview_id = accepted_interview["interview_id"]
    detail = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    questions = detail["questions"]

    client.post(
        f"/api/candidate/interviews/{interview_id}/answers",
        json={"interview_question_id": questions[0]["interview_question_id"], "content": "有内容"},
        headers=candidate_headers,
    )
    client.post(
        f"/api/candidate/interviews/{interview_id}/answers",
        json={"interview_question_id": questions[1]["interview_question_id"], "content": ""},
        headers=candidate_headers,
    )

    body = client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers).json()

    assert body["answered_count"] == 1


def test_submit_rejects_other_candidate(client, other_candidate_headers, accepted_interview):
    resp = client.post(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/submit",
        headers=other_candidate_headers,
    )

    assert resp.status_code == 403


def test_hr_can_still_overwrite_after_candidate_submits(client, hr_headers, candidate_headers, accepted_interview):
    """⚠️ 交卷只锁**候选人自己** —— HR 侧不受影响，仍可修订作答。

    修订后 `answer_source` **仍然是 `candidate`** —— 它记录的是「作答**最初**
    从哪条通道进来」，而不是「谁最后改的」。最后修改者（`answered_by`）**不在
    这个响应里下发**。两个事实在数据库里都存在，接口只暴露前者。
    这条用例防的是有人把 `answer_source` 改成「最后修改者」语义 —— 那会让
    「候选人有没有作答过」这个事实在 HR 覆盖后丢失。
    """
    interview_id = accepted_interview["interview_id"]
    detail = client.get(f"/api/candidate/interviews/{interview_id}", headers=candidate_headers).json()
    iq_id = detail["questions"][0]["interview_question_id"]
    client.post(
        f"/api/candidate/interviews/{interview_id}/answers",
        json={"interview_question_id": iq_id, "content": "候选人原文"},
        headers=candidate_headers,
    )
    client.post(f"/api/candidate/interviews/{interview_id}/submit", headers=candidate_headers)

    resp = client.post(
        f"/api/interviews/{interview_id}/answers",
        json={"interview_question_id": iq_id, "content": "HR 修订后的版本"},
        headers=hr_headers,
    )

    assert resp.status_code == 200, "HR 不受交卷锁影响"
    after = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    first = after["questions"][0]
    assert first["answer"] == "HR 修订后的版本", "内容确实被覆盖了"
    assert first["answer_source"] == "candidate", "「最初来自候选人」这个事实必须保留"


# ===========================================================================
# 10.7 关联 / 解除关联简历
# ===========================================================================


def test_link_resume_and_read_it_back(client, candidate_headers, accepted_interview, resume):
    interview_id = accepted_interview["interview_id"]

    linked = client.put(
        f"/api/candidate/interviews/{interview_id}/resume",
        json={"resume_id": resume.id},
        headers=candidate_headers,
    )

    assert linked.status_code == 200
    assert linked.json()["resume_id"] == resume.id

    listed = client.get("/api/candidate/interviews", headers=candidate_headers).json()
    assert listed[0]["resume_id"] == resume.id, "能写就必须能读"


def test_link_resume_replaces_previous_link(client, candidate_headers, accepted_interview, resume, db, candidate_user):
    from app.resume import service as resume_service
    from app.resume.schemas import ResumeCreate

    interview_id = accepted_interview["interview_id"]
    second = resume_service.create_resume(
        db, candidate_user, ResumeCreate(title="第二份", content="另一份简历的正文内容")
    )
    client.put(
        f"/api/candidate/interviews/{interview_id}/resume",
        json={"resume_id": resume.id},
        headers=candidate_headers,
    )

    replaced = client.put(
        f"/api/candidate/interviews/{interview_id}/resume",
        json={"resume_id": second.id},
        headers=candidate_headers,
    )

    assert replaced.status_code == 200
    assert replaced.json()["resume_id"] == second.id, "一场面试只关联一份，重复关联是替换"


def test_unlink_resume_with_null(client, candidate_headers, linked_interview):
    resp = client.put(
        f"/api/candidate/interviews/{linked_interview['interview_id']}/resume",
        json={"resume_id": None},
        headers=candidate_headers,
    )

    assert resp.status_code == 200
    assert resp.json() is None
    listed = client.get("/api/candidate/interviews", headers=candidate_headers).json()
    assert listed[0]["resume_id"] is None


def test_link_requires_the_field_explicitly(client, candidate_headers, accepted_interview):
    """⚠️ `resume_id` **必须传**（哪怕传 `null`）—— 缺字段是 400。

    「解除关联」与「这次没带这个字段」是两件事，不能混为一谈。
    """
    resp = client.put(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/resume",
        json={},
        headers=candidate_headers,
    )

    assert resp.status_code == 400


def test_link_other_candidates_resume_is_403(client, candidate_headers, accepted_interview, other_resume):
    resp = client.put(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/resume",
        json={"resume_id": other_resume.id},
        headers=candidate_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_link_nonexistent_resume_is_404(client, candidate_headers, accepted_interview):
    resp = client.put(
        f"/api/candidate/interviews/{accepted_interview['interview_id']}/resume",
        json={"resume_id": 424242},
        headers=candidate_headers,
    )

    assert resp.status_code == 404


def test_link_rejected_without_accepted_invitation(client, candidate_headers, hr_headers, position, resume):
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    resp = client.put(
        f"/api/candidate/interviews/{interview['id']}/resume",
        json={"resume_id": resume.id},
        headers=candidate_headers,
    )

    assert resp.status_code == 403


def test_link_rejected_after_completed(client, candidate_headers, hr_headers, linked_interview, resume):
    """面试结束即冻结：简历是面试的输入，不能事后改。"""
    interview_id = linked_interview["interview_id"]
    client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)

    resp = client.put(
        f"/api/candidate/interviews/{interview_id}/resume",
        json={"resume_id": resume.id},
        headers=candidate_headers,
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_link_succeeds_while_interview_still_ongoing(client, candidate_headers, linked_interview, resume, db, candidate_user):
    """进行中可以随时换关联 —— 换完 HR 需重新触发补题才生效（本次只验证写成功）。"""
    from app.resume import service as resume_service
    from app.resume.schemas import ResumeCreate

    second = resume_service.create_resume(
        db, candidate_user, ResumeCreate(title="更贴合的一份", content="与岗位更匹配的经历描述")
    )

    resp = client.put(
        f"/api/candidate/interviews/{linked_interview['interview_id']}/resume",
        json={"resume_id": second.id},
        headers=candidate_headers,
    )

    assert resp.status_code == 200


@pytest.mark.parametrize("headers_name", ["hr_headers", "admin_headers"])
def test_candidate_endpoints_reject_hr_side(client, request, headers_name, accepted_interview):
    """候选人侧守卫精确匹配：HR 与 admin 一律 403。"""
    headers = request.getfixturevalue(headers_name)
    iv = accepted_interview["interview_id"]

    assert client.get("/api/candidate/interviews", headers=headers).status_code == 403
    assert client.get(f"/api/candidate/interviews/{iv}", headers=headers).status_code == 403
    assert (
        client.post(
            f"/api/candidate/interviews/{iv}/answers",
            json={"interview_question_id": 1, "content": "x"},
            headers=headers,
        ).status_code
        == 403
    )
    assert client.post(f"/api/candidate/interviews/{iv}/submit", headers=headers).status_code == 403
    assert (
        client.put(
            f"/api/candidate/interviews/{iv}/resume", json={"resume_id": None}, headers=headers
        ).status_code
        == 403
    )
