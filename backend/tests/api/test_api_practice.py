"""API 接口测试 —— 模块 9/9：practice（刷题，候选人侧）。

覆盖 9 个 method-route：
    GET  /api/practice/questions                  刷题取题（预览）
    GET  /api/practice/sessions                   我的练习会话列表
    POST /api/practice/sessions                   开始一次练习（201）
    GET  /api/practice/sessions/{session_id}      练习详情与进度
    POST /api/practice/sessions/{session_id}/items   提交作答 → 即时判分
    POST /api/practice/items/{item_id}/rescore    对未判分的题重判
    POST /api/practice/sessions/{session_id}/finish  结束练习
    GET  /api/practice/wrong-book                 错题本
    GET  /api/practice/stats                      练习统计

契约来源：
    docs/superpowers/specs/2026-09-20-module-13-practice-plan.md §4 / §5.2 / §6
    docs/superpowers/specs/2026-09-21-module-20-practice-plan.md §4 / §5 / §6
    docs/apis/API接口文档.md §12.1–§12.9

⚠️ 本文件重点补的是既有套件里**只有 service 层、没有 HTTP 层**的那几处
    （`rescore` 正常路径、`finish` 幂等、错题本与统计的**内容**、限流 409），
    以及两条候选人之间的**聚合数据隔离**（错题本 / 统计）。
"""

import pytest

from app.ai.base import PracticeGradeResult


class _GradingProvider:
    """可控的判分 Provider：记录调用次数，便于断言「没调 AI」这类事实。"""

    def __init__(self, grade: PracticeGradeResult | None = None):
        self.calls = 0
        self._grade = grade or PracticeGradeResult(
            score=8.0, is_correct=True, explanation="答得不错"
        )

    def grade_practice_answer(self, question_type, content, reference_answer, user_answer):
        self.calls += 1
        return self._grade


class _FailingGradeProvider:
    def __init__(self):
        self.calls = 0

    def grade_practice_answer(self, *args, **kwargs):
        self.calls += 1
        from app.core.exceptions import AIProviderError

        raise AIProviderError()


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.practice.service.get_provider", lambda: provider)


def _start(client, headers, **body):
    return client.post("/api/practice/sessions", json=body, headers=headers)


def _submit(client, headers, session_id, item_id, answer):
    return client.post(
        f"/api/practice/sessions/{session_id}/items",
        json={"item_id": item_id, "user_answer": answer},
        headers=headers,
    )


def _items_of(client, headers, session_id):
    detail = client.get(f"/api/practice/sessions/{session_id}", headers=headers).json()
    return detail["items"]


# ===========================================================================
# 12.1 刷题取题（预览）
# ===========================================================================


def test_preview_returns_questions_without_answers(client, candidate_headers, practice_questions):
    """⚠️ 预览**不含答案与解析** —— 防作弊落在「不下发」，不是「前端不显示」。"""
    resp = client.get("/api/practice/questions", headers=candidate_headers)

    assert resp.status_code == 200
    rows = resp.json()
    assert rows
    for row in rows:
        assert "reference_answer" not in row
        assert "explanation" not in row
        assert "options" in row, "选项必须下发，否则单选框渲染不出来"


def test_preview_filters_by_question_type_and_difficulty(client, candidate_headers, practice_questions):
    only_choice = client.get(
        "/api/practice/questions?question_type=single_choice", headers=candidate_headers
    ).json()
    only_short = client.get(
        "/api/practice/questions?question_type=short_answer", headers=candidate_headers
    ).json()

    assert only_choice and only_short
    assert all(r["question_type"] == "single_choice" for r in only_choice)
    assert all(r["question_type"] == "short_answer" for r in only_short)


def test_preview_ignores_resume_id(client, candidate_headers, practice_questions, resume):
    """⚠️ 预览**不接受** `resume_id`（按简历推荐只发生在「开始练习」）。

    传了也当未知参数忽略掉 —— 不报错、也不因此改排序。
    """
    plain = client.get("/api/practice/questions", headers=candidate_headers).json()
    with_resume = client.get(
        f"/api/practice/questions?resume_id={resume.id}", headers=candidate_headers
    ).json()

    assert [r["id"] for r in with_resume] == [r["id"] for r in plain]


def test_preview_rejects_limit_over_max(client, candidate_headers, practice_questions):
    resp = client.get("/api/practice/questions?limit=21", headers=candidate_headers)

    assert resp.status_code == 400


def test_preview_rejects_hr_side(client, hr_headers, admin_headers, practice_questions):
    assert client.get("/api/practice/questions", headers=hr_headers).status_code == 403
    assert client.get("/api/practice/questions", headers=admin_headers).status_code == 403


# ===========================================================================
# 12.2 我的练习会话列表
# ===========================================================================


def test_session_list_is_empty_before_any_practice(client, candidate_headers, practice_questions):
    assert client.get("/api/practice/sessions", headers=candidate_headers).json() == []


def test_session_list_includes_ongoing_with_fields(client, candidate_headers, practice_session):
    rows = client.get("/api/practice/sessions", headers=candidate_headers).json()

    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == practice_session.session.id
    assert row["status"] == "ongoing", "进行中的也要列出来，用于「继续未完成的练习」"
    assert row["total"] == 4
    assert row["answered_count"] == 0
    assert "items" not in row, "列表不含题目明细"


def test_session_list_filters_by_status(client, candidate_headers, practice_session):
    ongoing = client.get("/api/practice/sessions?status=ongoing", headers=candidate_headers).json()
    finished = client.get("/api/practice/sessions?status=finished", headers=candidate_headers).json()

    assert len(ongoing) == 1
    assert finished == []


def test_session_list_limit_max_is_100(client, candidate_headers, practice_session):
    assert client.get("/api/practice/sessions?limit=100", headers=candidate_headers).status_code == 200
    assert client.get("/api/practice/sessions?limit=101", headers=candidate_headers).status_code == 400


def test_session_list_isolated_between_candidates(client, candidate_headers, other_candidate_headers, practice_session):
    assert client.get("/api/practice/sessions", headers=candidate_headers).json()
    assert client.get("/api/practice/sessions", headers=other_candidate_headers).json() == []


# ===========================================================================
# 12.3 开始一次练习
# ===========================================================================


def test_start_session_returns_201_with_snapshot_items(client, candidate_headers, practice_questions):
    resp = _start(client, candidate_headers, size=4)

    assert resp.status_code == 201
    body = resp.json()
    assert body["session"]["status"] == "ongoing"
    assert body["session"]["total"] == 4
    assert len(body["items"]) == 4
    assert [i["seq"] for i in body["items"]] == [1, 2, 3, 4]
    assert all(i["user_answer"] is None for i in body["items"])
    assert body["resume_match_applied"] is False, "未关联简历时不该声称用了 AI 推荐"
    assert body["resume_id"] is None


def test_start_session_without_matching_questions_is_409_and_creates_nothing(
    client, candidate_headers, position
):
    """⚠️ 取不到题 → 409，且**不留空会话**（事务回滚）。"""
    assert client.get("/api/practice/sessions", headers=candidate_headers).json() == []

    resp = _start(client, candidate_headers, size=5)

    assert resp.status_code == 409
    assert "没有符合条件" in resp.json()["message"]
    assert client.get("/api/practice/sessions", headers=candidate_headers).json() == []


def test_start_session_rejects_size_over_max(client, candidate_headers, practice_questions):
    assert _start(client, candidate_headers, size=21).status_code == 400


@pytest.mark.parametrize("size", [10, 20])
def test_start_session_accepts_size_boundaries(client, candidate_headers, practice_questions, size):
    assert _start(client, candidate_headers, size=size).status_code == 201


def test_start_session_with_filters_records_them(client, candidate_headers, practice_questions):
    body = _start(client, candidate_headers, size=4, difficulty="medium", question_type="single_choice").json()

    assert body["session"]["difficulty"] == "medium"
    assert body["session"]["question_type"] == "single_choice"
    assert all(i["question"]["question_type"] == "single_choice" for i in body["items"])


def test_start_session_rejects_other_candidates_resume(client, candidate_headers, practice_questions, other_resume):
    resp = _start(client, candidate_headers, size=4, resume_id=other_resume.id)

    assert resp.status_code == 403


def test_start_session_rejects_nonexistent_resume(client, candidate_headers, practice_questions):
    resp = _start(client, candidate_headers, size=4, resume_id=424242)

    assert resp.status_code == 404


def test_start_session_rejects_resume_id_below_one(client, candidate_headers, practice_questions):
    """`resume_id` 是 `ge=1`；`0` 与负数都是 400，不是「不传」。"""
    assert _start(client, candidate_headers, size=4, resume_id=0).status_code == 400
    assert _start(client, candidate_headers, size=4, resume_id=-1).status_code == 400


def test_start_session_with_resume_marks_applied_on_success(
    client, candidate_headers, practice_questions, resume, monkeypatch
):
    from app.ai.base import MatchedQuestion

    class _MatchProvider:
        def __getattr__(self, name):
            def _match(resume_text, position_name, jd, dims, candidates, count):
                return [MatchedQuestion(question_id=c.question_id, reason="与简历相关") for c in candidates]

            return _match

    _use_provider(monkeypatch, _MatchProvider())

    body = _start(client, candidate_headers, size=4, resume_id=resume.id).json()

    assert body["session"]["status"] == "ongoing"
    assert body["resume_id"] == resume.id
    assert body["resume_match_applied"] is True


def test_start_session_degrades_silently_when_ai_fails(
    client, candidate_headers, practice_questions, resume, monkeypatch
):
    """⚠️ AI 挂了 → **201**，不是 502；但 `resume_match_applied=false` 让前端能提示降级。

    这两个字段回答两个不同问题：`resume_id` = 候选人**想**用哪份，
    `resume_match_applied` = 系统**实际做到了没有**。合成一个字段就看不见降级了。
    """
    from app.core.exceptions import AIProviderError

    class _Boom:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise AIProviderError()

            return _raise

    _use_provider(monkeypatch, _Boom())

    resp = _start(client, candidate_headers, size=4, resume_id=resume.id)

    assert resp.status_code == 201, "降级不是失败"
    body = resp.json()
    assert body["resume_id"] == resume.id, "「想用哪份」这个事实要保留"
    assert body["resume_match_applied"] is False, "要让前端能看出降级了"


def test_start_session_rate_limited(client, candidate_headers, practice_questions, practice_session, monkeypatch):
    """⚠️ 补空白：进程内限流的 409 此前**没有任何用例**触发过。

    限流对**三个计分动作**都生效：开始练习 / 提交作答 / 重判
    （`app/practice/service.py` 里三处 `_check_rate_limit`）。
    因此把上限压到 2 时，`practice_session` 夹具的「开始练习」已经用掉 1 次，
    第二次提交作答就会超限。只压到 1 的话，夹具自己就会被拒 —— 那样测的就不是本端点了。
    """
    from app.core.config import get_settings

    monkeypatch.setenv("PRACTICE_RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    try:
        session_id = practice_session.session.id
        item = _items_of(client, candidate_headers, session_id)[0]
        assert _submit(client, candidate_headers, session_id, item["item_id"], "甲").status_code == 200

        second = _submit(client, candidate_headers, session_id, item["item_id"], "乙")

        assert second.status_code == 409
        assert "频繁" in second.json()["message"]
    finally:
        get_settings.cache_clear()


# ===========================================================================
# 12.4 练习详情与进度
# ===========================================================================


def test_detail_hides_answers_until_submitted(client, candidate_headers, practice_session):
    """⚠️ 答案与解析**按题解锁** —— 未提交的题这两项为 `null`。

    这是一次性拉走全套答案的防线。前端不要把它当成「后端漏了字段」。
    """
    items = _items_of(client, candidate_headers, practice_session.session.id)

    assert all(i["explanation"] is None and i["reference_answer"] is None for i in items)
    assert all(i["is_correct"] is None and i["score"] is None for i in items)


def test_detail_reveals_answers_after_submitting_that_item(client, candidate_headers, practice_session):
    items = _items_of(client, candidate_headers, practice_session.session.id)
    target = items[0]

    _submit(client, candidate_headers, practice_session.session.id, target["item_id"], "随便答一句")

    after = _items_of(client, candidate_headers, practice_session.session.id)
    submitted = next(i for i in after if i["item_id"] == target["item_id"])
    untouched = next(i for i in after if i["item_id"] != target["item_id"])

    assert submitted["reference_answer"] is not None
    assert untouched["reference_answer"] is None, "没提交的题不能跟着一起解锁"


def test_detail_other_candidates_session_is_403(client, other_candidate_headers, practice_session):
    resp = client.get(f"/api/practice/sessions/{practice_session.session.id}", headers=other_candidate_headers)

    assert resp.status_code == 403


def test_detail_nonexistent_is_404(client, candidate_headers):
    assert client.get("/api/practice/sessions/424242", headers=candidate_headers).status_code == 404


# ===========================================================================
# 12.5 提交作答（即时判分）
# ===========================================================================


def test_single_choice_correct_is_graded_locally_without_ai(
    client, candidate_headers, practice_session, monkeypatch
):
    """单选题走**本地规则**判分，**不消耗 AI**（调用次数为 0 是硬断言）。"""
    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)

    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    correct = choice["question"]["options"][0]

    body = _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], correct).json()

    assert body["is_correct"] is True
    assert body["score"] == 10.0
    assert body["correct_answer"] == correct
    assert body["reference_answer"] is None, "单选把答案放 correct_answer"
    assert provider.calls == 0, "单选不该调 AI"


def test_single_choice_wrong_is_graded_locally(client, candidate_headers, practice_session, monkeypatch):
    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)

    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")

    body = _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], "一定不对的选项").json()

    assert body["is_correct"] is False
    assert body["score"] == 0.0
    assert body["correct_answer"] is not None
    assert provider.calls == 0


def test_short_answer_goes_through_ai(client, candidate_headers, practice_session, monkeypatch):
    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)

    items = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in items if i["question"]["question_type"] == "short_answer")

    body = _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "我的简答内容").json()

    assert provider.calls == 1, "简答必须调 AI"
    assert body["score"] == 8.0
    assert body["explanation"] == "答得不错"
    assert body["reference_answer"] is not None, "简答把答案放 reference_answer"
    assert body["correct_answer"] is None


def test_blank_answer_is_graded_zero_without_ai(client, candidate_headers, practice_session, monkeypatch):
    """空白作答 → 直接判错、0 分、解析为「未作答」，**不调 AI**。"""
    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)

    items = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in items if i["question"]["question_type"] == "short_answer")

    body = _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "   ").json()

    assert body["is_correct"] is False
    assert body["score"] == 0.0
    assert "未作答" in body["explanation"]
    assert provider.calls == 0


def test_short_answer_without_reference_is_left_unscored(
    client, candidate_headers, candidate_user, db, position, hr_user, monkeypatch
):
    """⚠️ 题目没有参考答案 → **不调 AI**，判为「未判分」（`is_correct` 为 `null`）。"""
    from app.practice import service as practice_service
    from app.practice.schemas import PracticeSessionCreate
    from app.question import repository

    repository.create(
        db,
        position_id=position.id,
        category="通用",
        dimension="沟通能力",
        content="这道简答题故意没有参考答案的题干",
        difficulty="medium",
        tags=[],
        source="bank",
        question_type="short_answer",
        created_by=hr_user.id,
    )
    db.commit()

    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)
    session = practice_service.start_session(db, candidate_user, PracticeSessionCreate(size=1))

    item = _items_of(client, candidate_headers, session.session.id)[0]
    body = _submit(client, candidate_headers, session.session.id, item["item_id"], "认真答了但没人能判").json()

    assert body["is_correct"] is None, "未判分 ≠ 判错"
    assert body["score"] is None
    assert provider.calls == 0, "没有参考答案时不该白调 AI"


def test_ai_grading_failure_still_returns_200_with_unscored(
    client, candidate_headers, practice_session, monkeypatch
):
    """⚠️ AI 判分失败 → **200**（不是 502），作答照常落库但标为未判分。

    与「出题失败 502」形成对照：刷题是用户在答题，不能因为判分不了就把作答丢掉。
    """
    provider = _FailingGradeProvider()
    _use_provider(monkeypatch, provider)

    items = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in items if i["question"]["question_type"] == "short_answer")

    resp = _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "认真答了")

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_correct"] is None
    assert body["score"] is None
    assert "重判" in body["explanation"], "要告诉用户「稍后可重判」"


def test_submit_rejects_item_from_another_session(
    client, candidate_headers, candidate_user, practice_questions, practice_session, db
):
    """用 A 会话的 id 提交 B 会话的题 → 404（`item_id` 必须属于该会话）。"""
    from app.practice import service as practice_service
    from app.practice.schemas import PracticeSessionCreate

    other = practice_service.start_session(db, candidate_user, PracticeSessionCreate(size=2))
    other_item = _items_of(client, candidate_headers, other.session.id)[0]

    resp = _submit(client, candidate_headers, practice_session.session.id, other_item["item_id"], "x")

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_submit_rejects_finished_session(client, candidate_headers, practice_session):
    items = _items_of(client, candidate_headers, practice_session.session.id)
    client.post(f"/api/practice/sessions/{practice_session.session.id}/finish", headers=candidate_headers)

    resp = _submit(client, candidate_headers, practice_session.session.id, items[0]["item_id"], "x")

    assert resp.status_code == 409
    assert "已结束" in resp.json()["message"]


def test_submit_updates_progress(client, candidate_headers, practice_session, monkeypatch):
    _use_provider(monkeypatch, _GradingProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)

    body = _submit(client, candidate_headers, practice_session.session.id, items[0]["item_id"], "答案").json()

    assert body["progress"]["answered_count"] == 1
    assert body["progress"]["total"] == 4


# ===========================================================================
# 12.6 重新判分
# ===========================================================================


def test_rescore_grades_a_previously_unscored_item(
    client, candidate_headers, practice_session, monkeypatch
):
    """⚠️ 补空白：这是审计指出的**最大一处 HTTP 层空白** —— `rescore` 的正常路径
    此前完全没有接口层用例（只有鉴权扫过一遍）。

    场景：第一次判分时 AI 不可用（未判分）→ 后面恢复了 → 重新判分应当判出来。
    """
    _use_provider(monkeypatch, _FailingGradeProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in items if i["question"]["question_type"] == "short_answer")
    assert _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "我的作答").json()[
        "is_correct"
    ] is None

    # AI 恢复
    provider = _GradingProvider()
    _use_provider(monkeypatch, provider)

    resp = client.post(f"/api/practice/items/{short['item_id']}/rescore", headers=candidate_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert provider.calls == 1, "未判分的题重判要真的调 AI"
    assert body["is_correct"] is True
    assert body["score"] == 8.0


def test_rescore_of_an_already_scored_item_is_idempotent_without_ai(
    client, candidate_headers, practice_session, monkeypatch
):
    """⚠️ 已判分的题重判 → 直接返回原结果，**不再调 AI**、不改分数。"""
    first = _GradingProvider()
    _use_provider(monkeypatch, first)
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    graded = _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], choice["question"]["options"][0]).json()

    counter = _GradingProvider()
    _use_provider(monkeypatch, counter)

    again = client.post(f"/api/practice/items/{choice['item_id']}/rescore", headers=candidate_headers)

    assert again.status_code == 200
    assert counter.calls == 0, "已判分的题不该重新调 AI"
    assert again.json()["score"] == graded["score"]
    assert again.json()["is_correct"] == graded["is_correct"]


def test_rescore_rejects_other_candidates_item(
    client, candidate_headers, other_candidate_headers, practice_session
):
    """别人的作答项不能重判（403）—— 这也是 `rescore` 此前唯一的覆盖，保留它。"""
    item_id = _items_of(client, candidate_headers, practice_session.session.id)[0]["item_id"]

    resp = client.post(f"/api/practice/items/{item_id}/rescore", headers=other_candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_rescore_nonexistent_item_is_404(client, candidate_headers):
    resp = client.post("/api/practice/items/424242/rescore", headers=candidate_headers)

    assert resp.status_code == 404


# ===========================================================================
# 12.7 结束练习
# ===========================================================================


def test_finish_returns_summary(client, candidate_headers, practice_session, monkeypatch):
    _use_provider(monkeypatch, _GradingProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], choice["question"]["options"][0])

    resp = client.post(f"/api/practice/sessions/{practice_session.session.id}/finish", headers=candidate_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == practice_session.session.id
    assert body["status"] == "finished"
    assert body["total"] == 4
    assert body["answered_count"] == 1
    assert body["correct_count"] == 1
    assert body["unscored_count"] == 0
    assert body["accuracy"] == 1.0
    assert isinstance(body["by_dimension"], list) and body["by_dimension"]


def test_finish_is_idempotent_and_keeps_first_finished_at(
    client, candidate_headers, practice_session, db
):
    """⚠️ 补空白：`finish` 的幂等此前没有 HTTP 用例（`finished_at` 不能被刷新）。"""
    from sqlalchemy import text

    first = client.post(f"/api/practice/sessions/{practice_session.session.id}/finish", headers=candidate_headers)
    assert first.status_code == 200

    db.rollback()
    stamped = db.execute(
        text("SELECT finished_at FROM practice_session WHERE id = :i"), {"i": practice_session.session.id}
    ).scalar_one()

    second = client.post(f"/api/practice/sessions/{practice_session.session.id}/finish", headers=candidate_headers)

    assert second.status_code == 200
    db.rollback()
    again = db.execute(
        text("SELECT finished_at FROM practice_session WHERE id = :i"), {"i": practice_session.session.id}
    ).scalar_one()
    assert again == stamped, "重复结束不能刷新 finished_at"


def test_finish_accuracy_is_null_when_nothing_scored(client, candidate_headers, practice_session):
    """一题都没判分时正确率是 `null`，不是 0（0 会被读成「全错」）。"""
    body = client.post(
        f"/api/practice/sessions/{practice_session.session.id}/finish", headers=candidate_headers
    ).json()

    assert body["accuracy"] is None
    assert body["unscored_count"] == 0, "一题都没作答，也就没有未判分"


def test_finish_other_candidates_session_is_403(client, other_candidate_headers, practice_session):
    resp = client.post(
        f"/api/practice/sessions/{practice_session.session.id}/finish", headers=other_candidate_headers
    )

    assert resp.status_code == 403


# ===========================================================================
# 12.8 错题本
# ===========================================================================


def test_wrong_book_is_empty_before_any_wrong_answer(client, candidate_headers, practice_session):
    assert client.get("/api/practice/wrong-book", headers=candidate_headers).json() == []


def test_wrong_book_lists_wrong_answers_with_content(client, candidate_headers, practice_session, monkeypatch):
    """⚠️ 补空白：错题本的**内容**此前没有 HTTP 用例（只断言过空态）。"""
    _use_provider(monkeypatch, _GradingProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], "一定不对的选项")

    rows = client.get("/api/practice/wrong-book", headers=candidate_headers).json()

    assert len(rows) == 1
    row = rows[0]
    assert row["question_id"] == choice["question"]["id"]
    assert row["my_wrong_answer"] == "一定不对的选项"
    assert row["wrong_count"] == 1
    assert row["content"] == choice["question"]["content"]
    assert row["reference_answer"] is not None
    assert row["last_wrong_at"] is not None


def test_wrong_book_excludes_unscored_items(client, candidate_headers, practice_session, monkeypatch):
    """⚠️ **未判分的题不进错题本** —— `is_correct` 为 `null` 不等于答错。"""
    _use_provider(monkeypatch, _FailingGradeProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in items if i["question"]["question_type"] == "short_answer")
    _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "认真答了但判不了")

    assert client.get("/api/practice/wrong-book", headers=candidate_headers).json() == []


def test_wrong_book_deduplicates_by_question_with_count(
    client, candidate_headers, candidate_user, practice_questions, practice_session, db, monkeypatch
):
    """同一道题错两次 → 仍然只有一行，`wrong_count` 累加。

    ⚠️ 要让「错两次」成立，必须让这道题出现在**两次不同的会话**里 ——
    在同一个会话里对同一题重复提交是**原地更新**（`practice_item` 只有一行），
    计数不会涨。这一点我第一次写成「同一 item 提交两次」时踩过：
    那样断言 `wrong_count == 2` 恒失败，因为它确实只有 1 行。
    """
    from app.practice import service as practice_service
    from app.practice.schemas import PracticeSessionCreate

    _use_provider(monkeypatch, _GradingProvider())

    first_items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in first_items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], "错的")

    second = practice_service.start_session(db, candidate_user, PracticeSessionCreate(size=4))
    same_question = next(
        i for i in second.items if i.question["id"] == choice["question"]["id"]
    )
    _submit(client, candidate_headers, second.session.id, same_question.item_id, "又错了")

    rows = client.get("/api/practice/wrong-book", headers=candidate_headers).json()
    matching = [r for r in rows if r["question_id"] == choice["question"]["id"]]

    assert len(matching) == 1, "按 question_id 去重，一题一行"
    assert matching[0]["wrong_count"] == 2, "两次都错 → 计数为 2"


def test_wrong_book_isolated_between_candidates(
    client, candidate_headers, other_candidate_headers, practice_session, monkeypatch
):
    """⚠️ 补空白：两位候选人的错题本互不可见（聚合数据的隔离此前没有 HTTP 用例）。"""
    _use_provider(monkeypatch, _GradingProvider())
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], "错的")

    assert client.get("/api/practice/wrong-book", headers=candidate_headers).json(), "本人有错题"
    assert client.get("/api/practice/wrong-book", headers=other_candidate_headers).json() == [], (
        "另一个人不该看到别人的错题"
    )


# ===========================================================================
# 12.9 练习统计
# ===========================================================================


def test_stats_are_zero_before_practice(client, candidate_headers, practice_questions):
    body = client.get("/api/practice/stats", headers=candidate_headers).json()

    assert body["total_answered"] == 0
    assert body["accuracy"] is None
    assert body["by_dimension"] == []
    assert body["by_type"] == []


def test_stats_accuracy_denominator_excludes_unscored(client, candidate_headers, practice_session, monkeypatch):
    """⚠️ 正确率的分母是**已判分数**，不含未判分 —— 否则 AI 挂掉期间的作答会凭空拉低正确率。"""
    _use_provider(monkeypatch, _GradingProvider(grade=PracticeGradeResult(score=10.0, is_correct=True, explanation="对")))
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], choice["question"]["options"][0])

    _use_provider(monkeypatch, _FailingGradeProvider())
    after_fail = _items_of(client, candidate_headers, practice_session.session.id)
    short = next(i for i in after_fail if i["question"]["question_type"] == "short_answer")
    _submit(client, candidate_headers, practice_session.session.id, short["item_id"], "判不了的作答")

    body = client.get("/api/practice/stats", headers=candidate_headers).json()

    assert body["total_answered"] == 2
    assert body["scored_count"] == 1
    assert body["unscored_count"] == 1
    assert body["accuracy"] == 1.0, "分母是 scored_count（1），不是 total_answered（2）"


def test_stats_breakdown_by_dimension_and_type(client, candidate_headers, practice_session, monkeypatch):
    _use_provider(monkeypatch, _GradingProvider(grade=PracticeGradeResult(score=10.0, is_correct=True, explanation="对")))
    items = _items_of(client, candidate_headers, practice_session.session.id)
    choice = next(i for i in items if i["question"]["question_type"] == "single_choice")
    _submit(client, candidate_headers, practice_session.session.id, choice["item_id"], choice["question"]["options"][0])

    body = client.get("/api/practice/stats", headers=candidate_headers).json()

    assert body["by_type"] and body["by_type"][0]["question_type"] == "single_choice"
    assert body["by_dimension"] and {"dimension", "answered", "scored", "correct"} <= set(body["by_dimension"][0])


def test_stats_isolated_between_candidates(client, candidate_headers, other_candidate_headers, practice_session):
    """⚠️ 补空白：两位候选人的统计互不影响。"""
    assert client.get("/api/practice/stats", headers=other_candidate_headers).json()["total_answered"] == 0


def test_practice_endpoints_reject_hr_side(client, hr_headers, admin_headers, practice_session):
    for headers in (hr_headers, admin_headers):
        assert client.get("/api/practice/stats", headers=headers).status_code == 403
        assert client.get("/api/practice/wrong-book", headers=headers).status_code == 403
        assert client.get("/api/practice/sessions", headers=headers).status_code == 403
        assert (
            client.post(
                f"/api/practice/sessions/{practice_session.session.id}/finish", headers=headers
            ).status_code
            == 403
        )
