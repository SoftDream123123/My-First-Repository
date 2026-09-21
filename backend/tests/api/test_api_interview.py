"""API 接口测试 —— 模块 6/9：interview（面试，HR 侧）。

覆盖 15 个 method-route：
    POST   /api/interviews
    GET    /api/interviews
    GET    /api/interviews/{interview_id}
    PATCH  /api/interviews/{interview_id}
    POST   /api/interviews/{interview_id}/answers
    POST   /api/interviews/{interview_id}/complete
    POST   /api/interviews/{interview_id}/rollback
    POST   /api/interviews/{interview_id}/invitations
    GET    /api/interviews/{interview_id}/invitations
    DELETE /api/interviews/{interview_id}/invitations/{invitation_id}
    POST   /api/interviews/{interview_id}/prep
    GET    /api/interviews/{interview_id}/prep
    PUT    /api/interviews/{interview_id}/prep
    POST   /api/interviews/{interview_id}/questions/match
    GET    /api/interviews/{interview_id}/resume

（评估相关的 `evaluate` / `evaluation/stream` / `report` / `report/export` 属模块 7。）

契约来源：
    docs/superpowers/specs/2026-09-15-module-05-interview-plan.md §4 / §5.4 / §6
    docs/superpowers/specs/2026-09-20-module-12-interview-invitation-plan.md §4 / §6
    docs/superpowers/specs/2026-09-21-module-19-interview-plan.md §4 / §5 / §6
    docs/apis/API接口文档.md §8.1–§8.16

⚠️ 三处容易搞混、本文件专门分开测的「同名不同物」：
    · `source`（题目来源快照）vs `answer_source`（作答来源）
    · 「补题 0 条」（200，正常）vs「AI 失败」（502）vs「题库耗尽」（409）
    · 撤销邀请（**200 带响应体**）vs 岗位/题目/简历的删除（204 空体）
"""

import pytest

from app.ai.base import MatchedQuestion
from app.core.exceptions import AIProviderError

PREP_SECTIONS = ("outline", "focus_points", "question_plan")


def _create_interview(client, headers, position_id, name="张三", contact=None):
    payload = {"position_id": position_id, "candidate_name": name}
    if contact is not None:
        payload["candidate_contact"] = contact
    return client.post("/api/interviews", json=payload, headers=headers)


def _advance(client, headers, interview_id, status):
    """把面试推到指定状态（只走文档允许的迁移路径）。"""
    if status == "ongoing":
        return
    assert client.post(f"/api/interviews/{interview_id}/complete", headers=headers).status_code == 200
    if status == "completed":
        return
    raise AssertionError(f"本辅助函数不覆盖 {status}")


class _FakeProvider:
    """可控的假 Provider：只实现本模块用到的三个方法。

    `match_ids` 为 None 时表示「按传入候选池取前 count 个」——
    让补题用例的断言是确定性的，不必依赖 Mock 的启发式排序。
    """

    def __init__(self, generated=None, match_ids=None, match_reason="简历里提到过相关经历"):
        self._generated = generated or []
        self._match_ids = match_ids
        self._match_reason = match_reason

    def generate_questions(self, *args, count=0, **kwargs):
        return list(self._generated)[:count] or []

    def match_questions_by_resume(self, resume_text, position_name, jd, dims, candidates, count):
        if self._match_ids is None:
            picked = [c.question_id for c in candidates][:count]
        else:
            picked = list(self._match_ids)[:count]
        return [MatchedQuestion(question_id=qid, reason=self._match_reason) for qid in picked]


class _FailingProvider:
    """所有方法都炸 —— 用于验证 AI 失败时的降级 / 回滚语义。"""

    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise AIProviderError()

        return _boom


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.interview.service.get_provider", lambda: provider)


# ===========================================================================
# 8.2 创建面试（同步出题）
# ===========================================================================


def test_create_interview_returns_201_with_assembled_questions(client, hr_headers, position, practice_questions):
    """同步出题：一次请求就把题目组装完，面试直接进入 `ongoing`。"""
    resp = _create_interview(client, hr_headers, position.id)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ongoing", "draft → ongoing 在创建事务里完成"
    assert body["candidate_name"] == "张三"
    assert body["resume_id"] is None, "简历由候选人事后关联，创建时不接受"

    questions = body["questions"]
    assert len(questions) == 8, "默认 N(5) + M(3) = 8 题"
    assert [q["seq"] for q in questions] == list(range(1, 9)), "seq 从 1 连续"
    assert [q["interview_question_id"] for q in questions] == sorted(
        q["interview_question_id"] for q in questions
    )
    # 题库题在前、AI 题在后
    sources = [q["source"] for q in questions]
    assert sources == sorted(sources, key=lambda s: 0 if s == "bank" else 1), sources
    assert all(q["answer"] is None for q in questions)


def test_detail_uses_snapshot_after_bank_question_is_edited(client, hr_headers, position, db, practice_questions):
    """题库改题干后，**历史面试的题面不变**（快照在出题时写死）。"""
    created = _create_interview(client, hr_headers, position.id).json()
    snapshot_contents = [q["content"] for q in created["questions"]]

    from app.question import repository

    for bank_question in practice_questions:
        repository.update(db, bank_question, content="题干被彻底改写了")
    db.commit()

    after = client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()

    assert "题干被彻底改写了" not in [q["content"] for q in after["questions"]]
    assert [q["content"] for q in after["questions"]] == snapshot_contents


def test_create_interview_fills_up_to_eight_with_ai(client, hr_headers, position, db, hr_user, monkeypatch):
    """题库只有 2 题时，AI 要补足到 8 题。

    「N+M=8」是**总量**约束，不是「题库固定出 5 题」—— 题库不足时 AI 顶上，
    这条用例专门盯着这个容易被读成固定值的地方。
    """
    from app.ai.base import GeneratedQuestion
    from app.question import repository

    dimension = position.evaluation_dimensions[0]
    for i in (1, 2):
        repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension=dimension,
            content=f"题库里的第{i}道题的题干内容描述",
            difficulty="medium",
            tags=[],
            source="bank",
            created_by=hr_user.id,
        )
    db.commit()

    generated = [
        GeneratedQuestion(content=f"AI 生成的第{i}道题的题干内容", dimension=dimension)
        for i in range(1, 9)
    ]
    _use_provider(monkeypatch, _FakeProvider(generated=generated))

    body = _create_interview(client, hr_headers, position.id).json()

    assert len(body["questions"]) == 8
    assert sum(1 for q in body["questions"] if q["source"] == "bank") == 2
    assert sum(1 for q in body["questions"] if q["source"] == "ai") == 6


def test_create_interview_rejects_invisible_position(client, hr_headers, other_position):
    resp = _create_interview(client, hr_headers, other_position.id)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_create_interview_with_nonexistent_position_is_404(client, hr_headers):
    resp = _create_interview(client, hr_headers, 424242)

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "payload", [{}, {"position_id": 1}, {"position_id": 1, "candidate_name": ""}, {"position_id": 1, "candidate_name": "n" * 101}]
)
def test_create_interview_validation(client, hr_headers, payload):
    resp = client.post("/api/interviews", json=payload, headers=hr_headers)

    assert resp.status_code == 400, f"{payload} -> {resp.status_code} {resp.text}"


def test_create_interview_ai_failure_is_502_with_zero_residue(
    client, hr_headers, position, practice_questions, monkeypatch
):
    """⚠️ AI 出题失败 → 502，且**数据库里不留任何痕迹**（事务整体回滚）。

    只断言 502 是不够的：如果面试行留下了，用户会看到一条没有题目的空面试。
    """
    _use_provider(monkeypatch, _FailingProvider())

    resp = _create_interview(client, hr_headers, position.id)

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_PROVIDER_ERROR"
    assert client.get("/api/interviews", headers=hr_headers).json() == [], "不能留下半成品"


# ===========================================================================
# 8.3 面试列表
# ===========================================================================


def test_list_interviews_returns_only_own(client, hr_headers, other_hr_headers, position, other_position):
    mine = _create_interview(client, hr_headers, position.id).json()
    theirs = _create_interview(client, other_hr_headers, other_position.id, name="李四").json()

    resp = client.get("/api/interviews", headers=hr_headers)

    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert mine["id"] in ids
    assert theirs["id"] not in ids


def test_list_interviews_as_admin_sees_everyone(client, admin_headers, hr_headers, other_hr_headers, position, other_position):
    mine = _create_interview(client, hr_headers, position.id).json()
    theirs = _create_interview(client, other_hr_headers, other_position.id, name="李四").json()

    ids = {i["id"] for i in client.get("/api/interviews", headers=admin_headers).json()}

    assert {mine["id"], theirs["id"]} <= ids


def test_list_interviews_is_ordered_by_id_desc(client, hr_headers, position):
    first = _create_interview(client, hr_headers, position.id).json()
    second = _create_interview(client, hr_headers, position.id, name="李四").json()

    ids = [i["id"] for i in client.get("/api/interviews", headers=hr_headers).json()]

    assert ids == [second["id"], first["id"]], "新的在前"


def test_list_interviews_includes_aggregates(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    row = next(
        i for i in client.get("/api/interviews", headers=hr_headers).json() if i["id"] == created["id"]
    )

    assert row["position_name"] == position.name
    assert row["question_count"] == 8
    assert row["answered_count"] == 0
    assert "resume_id" not in row, "列表不下发 resume_id（只有详情下发）"


# ===========================================================================
# 8.4 面试详情
# ===========================================================================


def test_detail_questions_are_ordered_by_seq_and_answers_default_null(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    body = client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()

    assert [q["seq"] for q in body["questions"]] == list(range(1, 9))
    assert all(q["answer"] is None and q["recorded_at"] is None for q in body["questions"])
    assert body["question_count"] == 8
    assert body["resume_id"] is None


def test_detail_uses_snapshot_not_live_question(client, hr_headers, position, db, practice_questions):
    """面试题的 `content` / `dimension` 来自**快照**，题库改题不影响历史面试。"""
    created = _create_interview(client, hr_headers, position.id).json()
    bank_question = practice_questions[0]

    from app.question import repository

    repository.update(db, bank_question, content="题干被彻底改写了")
    db.commit()

    body = client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()
    contents = [q["content"] for q in body["questions"]]

    assert "题干被彻底改写了" not in contents, "历史面试必须用快照"


def test_detail_exposes_answer_source_separately_from_question_source(client, hr_headers, position, practice_questions):
    """`source`（题目来源）与 `answer_source`（作答来源）是两个字段。

    这条用例的价值在于防止有人「顺手把两个字段合成一个」。
    """
    created = _create_interview(client, hr_headers, position.id).json()
    iq_id = created["questions"][0]["interview_question_id"]

    client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": iq_id, "content": "我的回答"},
        headers=hr_headers,
    )

    first = client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()["questions"][0]

    assert first["answer_source"] == "hr"
    assert first["source"] in {"bank", "ai", "resume_match"}


def test_detail_other_owners_interview_is_403(client, hr_headers, other_hr_headers, other_position):
    theirs = _create_interview(client, other_hr_headers, other_position.id).json()

    resp = client.get(f"/api/interviews/{theirs['id']}", headers=hr_headers)

    assert resp.status_code == 403


def test_detail_nonexistent_is_404(client, hr_headers):
    assert client.get("/api/interviews/424242", headers=hr_headers).status_code == 404


# ===========================================================================
# 8.5 更新候选人信息
# ===========================================================================


def test_patch_updates_candidate_fields_only(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.patch(
        f"/api/interviews/{created['id']}",
        json={"candidate_name": "李四", "candidate_contact": "13900000000"},
        headers=hr_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_name"] == "李四"
    assert body["candidate_contact"] == "13900000000"
    assert body["status"] == "ongoing", "PATCH 不改状态"


def test_patch_can_clear_contact_with_null(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id, contact="13900000000").json()

    resp = client.patch(
        f"/api/interviews/{created['id']}", json={"candidate_contact": None}, headers=hr_headers
    )

    assert resp.status_code == 200
    assert resp.json()["candidate_contact"] is None, "null 在这里是「清空」"


def test_patch_is_allowed_after_completed_but_not_while_evaluating(
    client, hr_headers, position, practice_questions, db
):
    """⚠️ 冻结线在 **`evaluating` / `evaluated`**，`completed` 仍然可改。

    这是很容易记成「完成后就锁死」的地方：`completed` 表示「面试聊完了」，
    HR 仍可能要补正候选人联系方式；只有评估开始后，输入才真正冻结。
    """
    created = _create_interview(client, hr_headers, position.id).json()

    _advance(client, hr_headers, created["id"], "completed")
    after_completed = client.patch(
        f"/api/interviews/{created['id']}", json={"candidate_name": "张三丰"}, headers=hr_headers
    )
    assert after_completed.status_code == 200, "completed 下应允许修改"
    assert after_completed.json()["candidate_name"] == "张三丰"

    from app.interview import repository

    # `db` 会话早于 HTTP 请求打开，REPEATABLE READ 下看不到刚提交的行 —— 必须先结束事务
    db.rollback()
    interview = repository.get_by_id(db, created["id"])
    repository.update_interview(db, interview, status="evaluating")
    db.commit()

    while_evaluating = client.patch(
        f"/api/interviews/{created['id']}", json={"candidate_name": "改名"}, headers=hr_headers
    )
    assert while_evaluating.status_code == 409
    assert while_evaluating.json()["code"] == "BUSINESS_ERROR"


def test_patch_empty_body_is_a_noop(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.patch(f"/api/interviews/{created['id']}", json={}, headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json()["candidate_name"] == "张三"


# ===========================================================================
# 8.6 录入 / 修改回答
# ===========================================================================


def test_save_answer_then_update_in_place(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()
    iq_id = created["questions"][0]["interview_question_id"]

    first = client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": iq_id, "content": "第一次回答"},
        headers=hr_headers,
    )
    second = client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": iq_id, "content": "改过的回答"},
        headers=hr_headers,
    )

    assert first.status_code == second.status_code == 200
    detail = client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()
    assert detail["questions"][0]["answer"] == "改过的回答"
    assert detail["answered_count"] == 1, "更新而非新增"


def test_empty_answer_is_allowed_and_not_counted(client, hr_headers, position, practice_questions):
    """空串是**合法**作答（表示「问过了，没答上来」），但不计入 `answered_count`。"""
    created = _create_interview(client, hr_headers, position.id).json()
    iq_id = created["questions"][0]["interview_question_id"]

    resp = client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": iq_id, "content": ""},
        headers=hr_headers,
    )

    assert resp.status_code == 200
    assert client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()["answered_count"] == 0


def test_save_answer_rejects_over_10000_chars(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()
    iq_id = created["questions"][0]["interview_question_id"]

    resp = client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": iq_id, "content": "答" * 10001},
        headers=hr_headers,
    )

    assert resp.status_code == 400


def test_save_answer_with_foreign_question_is_404(client, hr_headers, position, practice_questions):
    """题目不属于该面试 → 404（防止用 A 面试的 id 往 B 面试里塞答案）。"""
    a = _create_interview(client, hr_headers, position.id).json()
    b = _create_interview(client, hr_headers, position.id, name="李四").json()

    resp = client.post(
        f"/api/interviews/{b['id']}/answers",
        json={"interview_question_id": a["questions"][0]["interview_question_id"], "content": "x"},
        headers=hr_headers,
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_save_answer_rejected_when_not_ongoing(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()
    _advance(client, hr_headers, created["id"], "completed")

    resp = client.post(
        f"/api/interviews/{created['id']}/answers",
        json={"interview_question_id": created["questions"][0]["interview_question_id"], "content": "x"},
        headers=hr_headers,
    )

    assert resp.status_code == 409
    assert "回退" in resp.json()["message"], "文案要告诉 HR 该怎么办"


# ===========================================================================
# 8.7 标记完成 / 8.8 回退
# ===========================================================================


def test_complete_sets_completed_at(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.post(f"/api/interviews/{created['id']}/complete", headers=hr_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None


def test_complete_is_not_idempotent(client, hr_headers, position, practice_questions):
    """重复标记完成 → 409（与「交卷」「撤销邀请」的幂等不同，别搞混）。"""
    created = _create_interview(client, hr_headers, position.id).json()
    _advance(client, hr_headers, created["id"], "completed")

    resp = client.post(f"/api/interviews/{created['id']}/complete", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"
    assert resp.json()["detail"]["from"] == "completed"


def test_rollback_from_completed_clears_completed_at(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()
    _advance(client, hr_headers, created["id"], "completed")

    resp = client.post(f"/api/interviews/{created['id']}/rollback", headers=hr_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ongoing"
    assert body["completed_at"] is None, "回退要清空完成时间"


def test_rollback_from_ongoing_is_409(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.post(f"/api/interviews/{created['id']}/rollback", headers=hr_headers)

    assert resp.status_code == 409


def test_complete_and_rollback_reject_candidate(client, candidate_headers, position, practice_questions, hr_headers):
    created = _create_interview(client, hr_headers, position.id).json()

    assert client.post(f"/api/interviews/{created['id']}/complete", headers=candidate_headers).status_code == 403
    assert client.post(f"/api/interviews/{created['id']}/rollback", headers=candidate_headers).status_code == 403


# ===========================================================================
# 8.9–8.11 作答邀请
# ===========================================================================


def test_create_invitation_returns_201_with_plaintext_code(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["accepted_at"] is None and body["candidate_username"] is None
    assert len(body["code"]) >= 20, "邀请码要够长、不可枚举"
    assert body["expires_at"] > body["created_at"], "有效期在未来"


def test_create_invitation_requires_ongoing(client, hr_headers, position, practice_questions):
    """`completed` 及之后不可再发邀请（入口在评估前就该收掉）。

    注：`draft` 在实践中难以从接口造出来（创建面试即出题并转 `ongoing`），
    因此这里只验证 `completed` 侧；`draft` 侧由 `test_generate_prep_on_draft_without_questions`
    的同类手法覆盖。
    """
    created = _create_interview(client, hr_headers, position.id).json()
    _advance(client, hr_headers, created["id"], "completed")

    resp = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_multiple_invitations_per_interview(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    a = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()
    b = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()

    assert a["id"] != b["id"]
    assert a["code"] != b["code"]


def test_list_invitations_empty_then_ordered_desc(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    assert client.get(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json() == []

    first = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()
    second = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()

    ids = [i["id"] for i in client.get(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()]

    assert ids == [second["id"], first["id"]]


def test_revoke_invitation_returns_200_with_body(client, hr_headers, position, practice_questions):
    """⚠️ 撤销是 **200 带响应体**，不是 204 —— 与岗位/题目/简历的删除不同。

    前端要拿 `status` 去更新列表那一行，所以这里必须真的有 body。
    """
    created = _create_interview(client, hr_headers, position.id).json()
    invitation = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()

    resp = client.delete(
        f"/api/interviews/{created['id']}/invitations/{invitation['id']}", headers=hr_headers
    )

    assert resp.status_code == 200
    assert resp.content, "不能是空响应体"
    assert resp.json()["status"] == "revoked"


def test_revoke_is_idempotent(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()
    invitation = client.post(f"/api/interviews/{created['id']}/invitations", headers=hr_headers).json()
    url = f"/api/interviews/{created['id']}/invitations/{invitation['id']}"

    assert client.delete(url, headers=hr_headers).status_code == 200
    again = client.delete(url, headers=hr_headers)

    assert again.status_code == 200, "已经撤销过的再撤销不报错"
    assert again.json()["status"] == "revoked"


def test_revoke_nonexistent_invitation_is_404(client, hr_headers, position, practice_questions):
    """⚠️ 补空白：不存在的邀请 id 此前没有用例。"""
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.delete(f"/api/interviews/{created['id']}/invitations/424242", headers=hr_headers)

    assert resp.status_code == 404


def test_revoke_invitation_of_another_interview_is_404(client, hr_headers, position, practice_questions):
    """邀请不属于该面试 → 404（不能跨面试撤销）。"""
    a = _create_interview(client, hr_headers, position.id).json()
    b = _create_interview(client, hr_headers, position.id, name="李四").json()
    invitation = client.post(f"/api/interviews/{a['id']}/invitations", headers=hr_headers).json()

    resp = client.delete(
        f"/api/interviews/{b['id']}/invitations/{invitation['id']}", headers=hr_headers
    )

    assert resp.status_code == 404


def test_invitation_endpoints_reject_candidate(client, candidate_headers, accepted_interview):
    """候选人不能自己去发 / 看 / 撤销邀请（那是 HR 的动作）。"""
    iv = accepted_interview
    assert client.post(f"/api/interviews/{iv['interview_id']}/invitations", headers=candidate_headers).status_code == 403
    assert client.get(f"/api/interviews/{iv['interview_id']}/invitations", headers=candidate_headers).status_code == 403
    assert (
        client.delete(
            f"/api/interviews/{iv['interview_id']}/invitations/{iv['invitation_id']}",
            headers=candidate_headers,
        ).status_code
        == 403
    )


# ===========================================================================
# 8.12–8.14 面试前准备助手
# ===========================================================================


def test_generate_prep_on_draft_without_questions(client, hr_headers, position, db):
    """⚠️ `draft` 且本场还没有题目时**也能生成** —— 准备助手是面试的前置工作稿。

    用接口建完面试再手工压回 `draft`：出题组装会把状态推到 `ongoing`，
    而本用例要验证的恰恰是「还没开始准备」的那种面试。
    """
    created = _create_interview(client, hr_headers, position.id).json()

    from app.interview import repository

    db.rollback()  # 同上：先结束旧事务，否则读不到 HTTP 刚提交的行
    repository.update_interview(db, repository.get_by_id(db, created["id"]), status="draft")
    db.commit()

    resp = client.post(f"/api/interviews/{created['id']}/prep", headers=hr_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["interview_id"] == created["id"]
    assert all(body[k] for k in PREP_SECTIONS), "三个部分要么都有要么都没有"
    assert body["edited_at"] is None, "AI 刚生成的还没有人工编辑"
    assert client.get(f"/api/interviews/{created['id']}", headers=hr_headers).json()["status"] == "draft", (
        "准备助手不进状态机"
    )


def test_get_prep_before_generation_is_404(client, hr_headers, position, practice_questions):
    created = _create_interview(client, hr_headers, position.id).json()

    resp = client.get(f"/api/interviews/{created['id']}/prep", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_regenerate_prep_overwrites_and_resets_edited_at(client, hr_headers, position, practice_questions, prep_payload):
    """重新生成 = 整体覆盖，且 `edited_at` **置回 null**。

    留着旧的 `edited_at` 会让界面谎称「已手工编辑」，而内容其实是 AI 的。
    """
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"
    assert client.post(url, headers=hr_headers).status_code == 200

    edited = client.put(url, json=prep_payload, headers=hr_headers)
    assert edited.status_code == 200
    assert edited.json()["edited_at"] is not None
    generated_at_before = edited.json()["generated_at"]

    regenerated = client.post(url, headers=hr_headers)

    assert regenerated.status_code == 200
    body = regenerated.json()
    assert body["edited_at"] is None, "覆盖后「已编辑」标记必须清掉"
    assert body["generated_at"] >= generated_at_before


def test_update_prep_requires_all_three_sections(client, hr_headers, position, practice_questions, prep_payload):
    """三个部分**必须都传** —— 整体覆盖，不做字段级合并。"""
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"
    client.post(url, headers=hr_headers)

    for missing in PREP_SECTIONS:
        partial = {k: v for k, v in prep_payload.items() if k != missing}
        resp = client.put(url, json=partial, headers=hr_headers)
        assert resp.status_code == 400, f"缺 {missing} 应 400，实际 {resp.status_code}"


def test_update_prep_before_generation_is_404_and_creates_nothing(
    client, hr_headers, position, practice_questions, prep_payload
):
    """未生成时 `PUT` 是 404，且**不会顺手建一条空的**出来。"""
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"

    assert client.put(url, json=prep_payload, headers=hr_headers).status_code == 404
    assert client.get(url, headers=hr_headers).status_code == 404


def test_prep_rejected_after_completed(client, hr_headers, position, practice_questions, prep_payload):
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"
    client.post(url, headers=hr_headers)
    _advance(client, hr_headers, created["id"], "completed")

    assert client.post(url, headers=hr_headers).status_code == 409
    assert client.get(url, headers=hr_headers).status_code == 200, "已生成的内容仍可读"
    assert client.put(url, json=prep_payload, headers=hr_headers).status_code == 409


def test_prep_ai_failure_keeps_existing_content(client, hr_headers, position, practice_questions, monkeypatch):
    """AI 失败 → 502，**已生成的旧内容一字不动**（含 generated_at）。"""
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"
    before = client.post(url, headers=hr_headers).json()

    _use_provider(monkeypatch, _FailingProvider())
    resp = client.post(url, headers=hr_headers)

    assert resp.status_code == 502
    after = client.get(url, headers=hr_headers).json()
    assert after == before, "失败后内容与时间戳都必须原样"


def test_prep_ai_failure_on_first_generation_leaves_no_row(client, hr_headers, position, practice_questions, monkeypatch):
    created = _create_interview(client, hr_headers, position.id).json()
    url = f"/api/interviews/{created['id']}/prep"

    _use_provider(monkeypatch, _FailingProvider())

    assert client.post(url, headers=hr_headers).status_code == 502
    assert client.get(url, headers=hr_headers).status_code == 404, "不能留下空行"


def test_prep_isolated_between_hrs(client, hr_headers, other_hr_headers, other_position, prep_payload):
    theirs = _create_interview(client, other_hr_headers, other_position.id).json()
    url = f"/api/interviews/{theirs['id']}/prep"

    assert client.post(url, headers=hr_headers).status_code == 403
    assert client.get(url, headers=hr_headers).status_code == 403
    assert client.put(url, json=prep_payload, headers=hr_headers).status_code == 403


# ===========================================================================
# 8.15 按简历补题
# ===========================================================================


def _match(client, headers, interview_id, **body):
    return client.post(
        f"/api/interviews/{interview_id}/questions/match", json=body, headers=headers
    )


def test_match_appends_with_source_and_reason(client, hr_headers, linked_interview, match_pool, monkeypatch):
    """补题只**追加**：新题的 `source` 是 `resume_match`、`match_reason` 非空，
    `seq` 续接本场最大值。"""
    interview_id = linked_interview["interview_id"]
    before = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    _use_provider(monkeypatch, _FakeProvider())

    resp = _match(client, hr_headers, interview_id, count=3)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["added_count"] == 3
    assert body["total_questions"] == before["question_count"] + 3
    assert all(item["match_reason"] for item in body["added"])

    after = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    added_seqs = [item["seq"] for item in body["added"]]
    assert added_seqs == list(range(before["question_count"] + 1, before["question_count"] + 4)), "seq 续接"
    new_questions = [q for q in after["questions"] if q["seq"] in added_seqs]
    assert all(q["source"] == "resume_match" for q in new_questions)
    # 既有题目不受影响
    old = [q for q in after["questions"] if q["seq"] not in added_seqs]
    assert all(q["match_reason"] is None for q in old), "非匹配来源的题 match_reason 必须为 null"


def test_match_is_idempotent_and_does_not_duplicate(
    client, hr_headers, linked_interview, match_pool, db, monkeypatch
):
    """⚠️ 幂等 = **不重复追加同一道题**，但仍会继续追加没出现过的题。

    判定重复不能用 `interview_question_id` —— 每次追加都会生成**新的**面试题行、
    拿到新的 id，两批之间永远无交集，那样断言恒真（本用例第一版就踩了这个坑）。
    真正的判据是「同一道**题库题**在本场出现两次」，所以按题干内容判定；
    另加一条数据库层的行数 / 去重数比对兜底。
    """
    from sqlalchemy import text

    interview_id = linked_interview["interview_id"]
    _use_provider(monkeypatch, _FakeProvider())

    first = _match(client, hr_headers, interview_id, count=2).json()
    second = _match(client, hr_headers, interview_id, count=2).json()
    assert first["added_count"] == 2 and second["added_count"] == 2

    detail = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    contents = [q["content"] for q in detail["questions"]]
    assert len(contents) == len(set(contents)), f"同一道题被追加了两次：{contents}"

    db.rollback()
    rows = db.execute(
        text("SELECT COUNT(*), COUNT(DISTINCT question_id) FROM interview_question WHERE interview_id = :i"),
        {"i": interview_id},
    ).one()
    assert rows[0] == rows[1], f"面试题行数 {rows[0]} 与去重后的题库题数 {rows[1]} 不等"


def test_match_returns_200_with_zero_when_ai_finds_nothing(client, hr_headers, linked_interview, match_pool, monkeypatch):
    """⚠️ 与「失败」严格区分：AI 认为没有更相关的题 → **200 + added_count=0**。"""
    interview_id = linked_interview["interview_id"]
    _use_provider(monkeypatch, _FakeProvider(match_ids=[]))

    resp = _match(client, hr_headers, interview_id, count=3)

    assert resp.status_code == 200
    assert resp.json()["added_count"] == 0
    assert resp.json()["added"] == []


def test_match_ai_failure_is_502_and_changes_nothing(client, hr_headers, linked_interview, match_pool, monkeypatch):
    """⚠️ 与「0 条」严格区分：AI 挂了 → 502，既有题目与面试状态都不动。"""
    interview_id = linked_interview["interview_id"]
    before = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    _use_provider(monkeypatch, _FailingProvider())

    resp = _match(client, hr_headers, interview_id, count=3)

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_PROVIDER_ERROR"
    after = client.get(f"/api/interviews/{interview_id}", headers=hr_headers).json()
    assert after["question_count"] == before["question_count"]
    assert after["status"] == before["status"] == "ongoing"


def test_match_requires_linked_resume(client, hr_headers, accepted_interview, match_pool):
    """未关联简历 → 409，文案要能指导前端隐藏/禁用按钮。"""
    resp = _match(client, hr_headers, accepted_interview["interview_id"], count=3)

    assert resp.status_code == 409
    assert "简历" in resp.json()["message"]


def test_match_requires_ongoing(client, hr_headers, linked_interview, match_pool):
    _advance(client, hr_headers, linked_interview["interview_id"], "completed")

    resp = _match(client, hr_headers, linked_interview["interview_id"], count=3)

    assert resp.status_code == 409


@pytest.mark.parametrize("count", [0, -1, 21])
def test_match_rejects_count_out_of_range(client, hr_headers, linked_interview, match_pool, count):
    """`count` 是 1–20；**`0` 也要拒绝**（想「不补题」就别调这个接口）。"""
    resp = _match(client, hr_headers, linked_interview["interview_id"], count=count)

    assert resp.status_code == 400, f"count={count} -> {resp.status_code}"


def test_match_rejects_candidate_and_other_hr(client, candidate_headers, other_hr_headers, linked_interview, match_pool):
    interview_id = linked_interview["interview_id"]

    assert _match(client, candidate_headers, interview_id, count=1).status_code == 403
    assert _match(client, other_hr_headers, interview_id, count=1).status_code == 403


def test_match_when_pool_exhausted_is_409(client, hr_headers, linked_interview, match_pool, monkeypatch):
    """候选池被抽干后 → 409（这是「没有可补的题」，不是「AI 说没有」）。"""
    interview_id = linked_interview["interview_id"]
    _use_provider(monkeypatch, _FakeProvider())
    total_pool = len(match_pool)

    # 反复补到池子耗尽（每道题最多出现一次）
    for _ in range(total_pool + 2):
        resp = _match(client, hr_headers, interview_id, count=20)
        if resp.status_code == 409:
            break

    assert resp.status_code == 409
    assert "没有可补充" in resp.json()["message"] or "可补充" in resp.json()["message"]


# ===========================================================================
# 8.16 读取面试关联的简历
# ===========================================================================


def test_hr_reads_linked_resume(client, hr_headers, linked_interview, resume):
    resp = client.get(f"/api/interviews/{linked_interview['interview_id']}/resume", headers=hr_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["resume_id"] == resume.id
    assert body["title"] == resume.title
    assert body["content"] == resume.content
    assert "created_by" not in body, "HR 不需要知道候选人的 user id"


def test_hr_reads_unlinked_resume_as_404_not_403(client, hr_headers, accepted_interview):
    """⚠️ 未关联返回 **404 而不是 403** —— 前端据此显示「候选人尚未提供简历」。"""
    resp = client.get(f"/api/interviews/{accepted_interview['interview_id']}/resume", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_hr_cannot_read_resume_of_another_hrs_interview(client, hr_headers, other_hr_headers, linked_interview):
    """判据是「这场面试属于我」，不是简历归谁 —— 换个 HR 就直接 403。"""
    resp = client.get(
        f"/api/interviews/{linked_interview['interview_id']}/resume", headers=other_hr_headers
    )

    assert resp.status_code == 403


def test_candidate_cannot_read_hr_resume_endpoint(client, candidate_headers, linked_interview):
    resp = client.get(
        f"/api/interviews/{linked_interview['interview_id']}/resume", headers=candidate_headers
    )

    assert resp.status_code == 403


def test_hr_reads_nonexistent_interview_resume_is_404(client, hr_headers):
    assert client.get("/api/interviews/424242/resume", headers=hr_headers).status_code == 404
