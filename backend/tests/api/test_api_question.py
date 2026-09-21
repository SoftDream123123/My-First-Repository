"""API 接口测试 —— 模块 4/9：question（题库）。

覆盖 6 个 method-route：
    POST   /api/questions
    GET    /api/questions
    GET    /api/questions/{question_id}
    PUT    /api/questions/{question_id}
    DELETE /api/questions/{question_id}
    POST   /api/questions/{question_id}/reference-answer

契约来源：
    docs/superpowers/specs/2026-09-15-module-03-question-plan.md §4 / §6
    docs/superpowers/specs/2026-09-20-module-10-question-plan.md §4.3 / §6
    docs/apis/API接口文档.md §7.1–§7.6

⚠️ 两处容易写错的地方，本文件刻意写清：
    · 列表接口**没有 `difficulty` 参数**（该筛选只在刷题侧存在）。
      既有套件里有一条用例给它传了 `difficulty` 却断言通过 —— 那是假覆盖，
      FastAPI 会静默忽略未知查询参数（见 test_list_ignores_unknown_query_params）。
    · 维度的「去重规则」是**判重后 400**，而标签是**静默去重**。两者口径不同。
"""

import pytest

from app.ai.base import ReferenceAnswerResult


def _create(client, headers, position_id, **overrides):
    """建题的薄封装，返回原始 Response 以便调用方各自断言。"""
    payload = {
        "position_id": position_id,
        "category": "通用",
        "dimension": "沟通能力",
        "content": "请描述一次你处理线上故障的完整过程。",
        "difficulty": "medium",
        "tags": [],
    }
    payload.update(overrides)
    return client.post("/api/questions", json=payload, headers=headers)


def _seed(db, position, owner, **overrides):
    """直接落库造题（前置数据走 HTTP 只会更脆）。"""
    from app.question import repository

    fields = {
        "position_id": position.id,
        "category": "通用",
        "dimension": "沟通能力",
        "content": "请描述一次你处理线上故障的完整过程。",
        "difficulty": "medium",
        "tags": [],
        "source": "bank",
        "created_by": owner.id,
    }
    fields.update(overrides)
    question = repository.create(db, **fields)
    db.commit()
    db.refresh(question)
    return question


# ===========================================================================
# 7.1 创建题目
# ===========================================================================


def test_create_question_returns_201_with_defaults(client, hr_headers, position):
    resp = _create(client, hr_headers, position.id)

    assert resp.status_code == 201
    body = resp.json()
    assert body["category"] == "通用"
    assert body["difficulty"] == "medium"
    assert body["question_type"] == "short_answer", "默认简答：存量题都是纯文本题"
    assert body["options"] == []
    assert body["reference_answer"] is None
    assert body["explanation"] is None
    assert body["tags"] == []
    assert body["source"] == "bank"


def test_create_question_ignores_client_supplied_source(client, hr_headers, position):
    """`source` 只由服务端在 AI 出题时写入 —— 客户端传 `ai` 也必须落 `bank`。"""
    resp = _create(client, hr_headers, position.id, source="ai")

    assert resp.status_code == 201
    assert resp.json()["source"] == "bank"


def test_create_question_dimension_must_belong_to_position(client, hr_headers, position):
    """维度不属于岗位的评估维度 → 400，且 `detail.allowed` 给出合法取值。"""
    resp = _create(client, hr_headers, position.id, dimension="不存在的维度")

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"]["allowed"] == position.evaluation_dimensions


def test_create_question_dimension_match_is_strip_sensitive_but_not_case_sensitive(client, hr_headers, position):
    """维度匹配是 **strip 后精确**匹配：两侧空白被容忍，大小写仍要一致。"""
    client.put(
        f"/api/positions/{position.id}",
        json={"name": position.name, "jd": "JD", "evaluation_dimensions": ["Communication"]},
        headers=hr_headers,
    )

    stripped = _create(client, hr_headers, position.id, dimension="  Communication  ")
    wrong_case = _create(client, hr_headers, position.id, dimension="communication")

    assert stripped.status_code == 201, "两侧空白应被 strip 后匹配成功"
    assert wrong_case.status_code == 400, "大小写不同不算同一维度"


def test_create_question_with_other_owners_position_is_403(client, hr_headers, other_position):
    resp = _create(client, hr_headers, other_position.id)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_create_question_with_nonexistent_position_is_404(client, hr_headers):
    resp = _create(client, hr_headers, 424242)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize("length,want", [(4, 400), (5, 201), (2000, 201), (2001, 400)])
def test_create_question_content_length_boundaries(client, hr_headers, position, length, want):
    """题干 5–2000 字符，四个边界逐个钉死（只测中间值会让 off-by-one 溜过去）。"""
    resp = _create(client, hr_headers, position.id, content="题" * length)

    assert resp.status_code == want, f"长度 {length} -> {resp.status_code} {resp.text}"


def test_create_question_tags_are_silently_deduplicated(client, hr_headers, position):
    """标签是**静默去重**（与维度不同 —— 维度判重会 400）。"""
    resp = _create(client, hr_headers, position.id, tags=["网络", "网络", " 网络 "])

    assert resp.status_code == 201
    assert resp.json()["tags"] == ["网络"]


@pytest.mark.parametrize(
    "tags",
    [["t"] * 11, [""], ["   "], ["t" * 21]],
)
def test_create_question_rejects_bad_tags(client, hr_headers, position, tags):
    resp = _create(client, hr_headers, position.id, tags=tags)

    assert resp.status_code == 400, f"{tags} -> {resp.status_code} {resp.text}"


# ---------- 单选题的三个字段是一组约束 ----------


def test_create_single_choice_question_with_valid_options(client, hr_headers, position):
    resp = _create(
        client,
        hr_headers,
        position.id,
        question_type="single_choice",
        options=["未认证", "未授权", "资源不存在"],
        reference_answer="未认证",
        explanation="401 表示身份未认证。",
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["question_type"] == "single_choice"
    assert body["options"] == ["未认证", "未授权", "资源不存在"]
    assert body["reference_answer"] == "未认证"


def test_single_choice_answer_matching_ignores_surrounding_whitespace(client, hr_headers, position):
    """参考答案与选项的相等判定是 strip 后比较（照抄选项时会带上空白）。"""
    resp = _create(
        client,
        hr_headers,
        position.id,
        question_type="single_choice",
        options=["未认证", "未授权"],
        reference_answer="  未认证  ",
    )

    assert resp.status_code == 201


@pytest.mark.parametrize(
    "overrides,message_part",
    [
        ({"question_type": "single_choice", "options": ["只有一个"], "reference_answer": "只有一个"}, "至少需要 2 个选项"),
        ({"question_type": "single_choice", "options": ["A", "A"], "reference_answer": "A"}, "选项不能重复"),
        ({"question_type": "single_choice", "options": ["A", "B"]}, "必须提供参考答案"),
        ({"question_type": "single_choice", "options": ["A", "B"], "reference_answer": "C"}, "必须是选项之一"),
        ({"question_type": "short_answer", "options": ["A", "B"]}, "不应包含选项"),
    ],
)
def test_question_type_field_group_rules(client, hr_headers, position, overrides, message_part):
    """单选/简答的跨字段约束逐条验证，并断言**文案能把问题指出来**。

    只断言 400 不够 —— 前端要把 `message` 直接展示给 HR，文案指错了地方
    （比如「选项不能重复」却报成「至少需要 2 个选项」）会让人改错字段。
    """
    resp = _create(client, hr_headers, position.id, **overrides)

    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert message_part in body["message"] or message_part in resp.text


def test_create_question_rejects_explanation_over_limit(client, hr_headers, position):
    resp = _create(client, hr_headers, position.id, explanation="e" * 2001)

    assert resp.status_code == 400


# ===========================================================================
# 7.2 题目列表
# ===========================================================================


def test_list_questions_returns_only_own(client, hr_headers, hr_user, other_hr, db, position, other_position):
    mine = _seed(db, position, hr_user)
    theirs = _seed(db, other_position, other_hr)

    resp = client.get("/api/questions", headers=hr_headers)

    assert resp.status_code == 200
    ids = [q["id"] for q in resp.json()]
    assert mine.id in ids
    assert theirs.id not in ids, "隔离键是题目自己的 created_by"


def test_list_questions_as_admin_sees_everyone(client, admin_headers, hr_user, other_hr, db, position, other_position):
    mine = _seed(db, position, hr_user)
    theirs = _seed(db, other_position, other_hr)

    ids = {q["id"] for q in client.get("/api/questions", headers=admin_headers).json()}

    assert {mine.id, theirs.id} <= ids


def test_list_questions_filters_combine_with_and(client, hr_headers, db, position, hr_user):
    a = _seed(db, position, hr_user, category="基础", dimension="沟通能力", content="甲题的内容描述文本")
    b = _seed(db, position, hr_user, category="进阶", dimension="专业能力", content="乙题的内容描述文本")

    only_a = client.get("/api/questions?category=基础&dimension=沟通能力", headers=hr_headers)
    only_b = client.get("/api/questions?category=进阶", headers=hr_headers)

    assert [q["id"] for q in only_a.json()] == [a.id]
    assert [q["id"] for q in only_b.json()] == [b.id]


def test_list_questions_is_ordered_by_id_ascending(client, hr_headers, db, position, hr_user):
    first = _seed(db, position, hr_user, content="第一题的内容描述文本")
    second = _seed(db, position, hr_user, content="第二题的内容描述文本")

    ids = [q["id"] for q in client.get("/api/questions", headers=hr_headers).json()]

    assert ids == [first.id, second.id]


def test_list_questions_keyword_matches_content(client, hr_headers, db, position, hr_user):
    hit = _seed(db, position, hr_user, content="关于缓存穿透的排查思路")
    _seed(db, position, hr_user, content="完全不相干的一道题目")

    ids = [q["id"] for q in client.get("/api/questions?keyword=缓存穿透", headers=hr_headers).json()]

    assert ids == [hit.id]


def test_list_questions_filters_by_question_type(client, hr_headers, db, position, hr_user):
    choice = _seed(
        db,
        position,
        hr_user,
        content="单选题的题干内容描述",
        question_type="single_choice",
        options=["A", "B"],
        reference_answer="A",
    )
    _seed(db, position, hr_user, content="简答题的题干内容描述", question_type="short_answer")

    ids = [
        q["id"]
        for q in client.get("/api/questions?question_type=single_choice", headers=hr_headers).json()
    ]

    assert ids == [choice.id]


def test_list_questions_does_not_support_difficulty_filter(client, hr_headers, db, position, hr_user):
    """⚠️ 记录真实契约：**HR 列表接口没有 `difficulty` 参数**。

    FastAPI 会静默忽略未知查询参数，所以传 `?difficulty=hard` 不会报错，
    也**不会**真的筛选 —— 结果与不传完全一样。这一条存在的意义是防止
    「测试里写了筛选、实际没筛」这种假覆盖（既有套件里就有这么一条）。
    """
    _seed(db, position, hr_user, difficulty="easy", content="简单题的题干内容描述")
    hard = _seed(db, position, hr_user, difficulty="hard", content="困难题的题干内容描述")

    filtered = client.get("/api/questions?difficulty=hard", headers=hr_headers)
    unfiltered = client.get("/api/questions", headers=hr_headers)

    assert filtered.json() == unfiltered.json(), "传了也不筛 —— 参数被忽略"
    assert hard.id in [q["id"] for q in filtered.json()]


def test_list_questions_unknown_query_params_are_ignored(client, hr_headers, db, position, hr_user):
    """未知查询参数一律忽略（不报 400）—— 这是 FastAPI 的默认行为，写下来免得被当成 bug。"""
    _seed(db, position, hr_user)

    resp = client.get("/api/questions?totally_unknown=1", headers=hr_headers)

    assert resp.status_code == 200


# ===========================================================================
# 7.3 题目详情
# ===========================================================================


def test_get_question_returns_200_for_owner(client, hr_headers, db, position, hr_user):
    question = _seed(db, position, hr_user)

    resp = client.get(f"/api/questions/{question.id}", headers=hr_headers)

    assert resp.status_code == 200
    assert resp.json()["id"] == question.id


def test_get_other_owners_question_is_403(client, hr_headers, db, other_position, other_hr):
    theirs = _seed(db, other_position, other_hr)

    resp = client.get(f"/api/questions/{theirs.id}", headers=hr_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_get_nonexistent_question_is_404(client, hr_headers):
    resp = client.get("/api/questions/424242", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ===========================================================================
# 7.4 更新题目
# ===========================================================================


def test_update_question_replaces_tags_entirely(client, hr_headers, db, position, hr_user):
    question = _seed(db, position, hr_user, tags=["旧标签", "另一个"])

    resp = client.put(
        f"/api/questions/{question.id}",
        json={
            "position_id": position.id,
            "dimension": "沟通能力",
            "content": "改过的题干内容描述文本",
            "tags": ["新标签"],
        },
        headers=hr_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["tags"] == ["新标签"], "全量替换，不是追加"


def test_update_question_keeps_mvp2_fields_when_omitted(client, hr_headers, db, position, hr_user):
    """⚠️ 关键语义：四个 MVP-2 新字段**缺省 = 保持不变**。

    若哪天有人给 `question_type` 加上 `short_answer` 的默认值，
    HR 只改个题干就会把单选题静默翻成简答题 —— 这条用例会立刻红。
    """
    question = _seed(
        db,
        position,
        hr_user,
        question_type="single_choice",
        options=["A", "B"],
        reference_answer="A",
        explanation="原解析",
    )

    resp = client.put(
        f"/api/questions/{question.id}",
        json={
            "position_id": position.id,
            "dimension": "沟通能力",
            "content": "只改了题干，其他都没传",
        },
        headers=hr_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["question_type"] == "single_choice", "不能被静默翻成简答"
    assert body["options"] == ["A", "B"]
    assert body["reference_answer"] == "A"
    assert body["explanation"] == "原解析"


def test_update_question_revalidates_dimension_when_position_changes(
    client, hr_headers, db, position, other_position, hr_user
):
    """换岗位时，维度要在**新岗位**的维度集合里重新校验。"""
    # 给 hr_user 再建一个维度不同的岗位，避免跨 HR 的 403 干扰本用例
    from app.position import service as position_service
    from app.position.schemas import PositionCreate

    narrow = position_service.create_position(
        db, hr_user, PositionCreate(name="窄维度岗位", jd="JD", evaluation_dimensions=["逻辑思维"])
    )
    question = _seed(db, position, hr_user, dimension="沟通能力")

    ineligible = client.put(
        f"/api/questions/{question.id}",
        json={"position_id": narrow.id, "dimension": "沟通能力", "content": "换岗位后的题干内容"},
        headers=hr_headers,
    )
    eligible = client.put(
        f"/api/questions/{question.id}",
        json={"position_id": narrow.id, "dimension": "逻辑思维", "content": "换岗位后的题干内容"},
        headers=hr_headers,
    )

    assert ineligible.status_code == 400, "新岗位没有「沟通能力」维度"
    assert eligible.status_code == 200


def test_update_nonexistent_question_is_404(client, hr_headers, position):
    resp = client.put(
        "/api/questions/424242",
        json={"position_id": position.id, "dimension": "沟通能力", "content": "随便什么内容"},
        headers=hr_headers,
    )

    assert resp.status_code == 404


# ===========================================================================
# 7.5 删除题目
# ===========================================================================


def test_delete_question_returns_204_with_empty_body(client, hr_headers, db, position, hr_user):
    question = _seed(db, position, hr_user)

    resp = client.delete(f"/api/questions/{question.id}", headers=hr_headers)

    assert resp.status_code == 204
    assert resp.content == b""


def test_delete_question_referenced_by_interview_is_409(client, hr_headers, db, position, hr_user):
    question = _seed(db, position, hr_user)
    created = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    )
    assert created.status_code == 201, "出题会抽到刚建的这道题"

    resp = client.delete(f"/api/questions/{question.id}", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"


def test_delete_nonexistent_question_is_404(client, hr_headers):
    """⚠️ 补空白：`DELETE` 对不存在 id 此前没有用例。"""
    resp = client.delete("/api/questions/424242", headers=hr_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ===========================================================================
# 7.6 生成参考答案与解析（AI 交互）
# ===========================================================================


class _FakeProvider:
    """只实现本端点用到的那一个方法，便于精确控制 AI 的「回答」。"""

    def __init__(self, reference_answer: str, explanation: str = "AI 给的解析"):
        self._answer = reference_answer
        self._explanation = explanation

    def generate_reference_answer(self, question_type, content, options, dimension):
        return ReferenceAnswerResult(
            reference_answer=self._answer, explanation=self._explanation
        )


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.question.service.get_provider", lambda: provider)


def test_generate_reference_answer_writes_back_and_returns_200(
    client, hr_headers, db, position, hr_user, monkeypatch
):
    question = _seed(db, position, hr_user, question_type="short_answer")
    _use_provider(monkeypatch, _FakeProvider("AI 给的参考答案"))

    resp = client.post(f"/api/questions/{question.id}/reference-answer", headers=hr_headers)

    assert resp.status_code == 200, "更新已有资源 → 200，不是 201"
    body = resp.json()
    assert body["reference_answer"] == "AI 给的参考答案"
    assert body["explanation"] == "AI 给的解析"

    # 真的落库了（换一个连接读）
    db.rollback()
    assert client.get(f"/api/questions/{question.id}", headers=hr_headers).json()[
        "reference_answer"
    ] == "AI 给的参考答案"


def test_generate_reference_answer_rejects_answer_outside_options(
    client, hr_headers, db, position, hr_user, monkeypatch
):
    """单选题 AI 给了选项外的答案 → 409，且**题目内容一字不改**。

    不做「吸附到最接近的选项」是刻意的：静默改写等于伪造正确答案。
    """
    question = _seed(
        db,
        position,
        hr_user,
        question_type="single_choice",
        options=["A", "B"],
        reference_answer="A",
    )
    _use_provider(monkeypatch, _FakeProvider("完全不存在的选项"))

    resp = client.post(f"/api/questions/{question.id}/reference-answer", headers=hr_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "BUSINESS_ERROR"

    db.rollback()
    after = client.get(f"/api/questions/{question.id}", headers=hr_headers).json()
    assert after["reference_answer"] == "A", "原答案必须原样保留"


def test_generate_reference_answer_ai_failure_is_502_and_changes_nothing(
    client, hr_headers, db, position, hr_user, monkeypatch
):
    from app.core.exceptions import AIProviderError

    question = _seed(db, position, hr_user, question_type="short_answer")

    class _Boom:
        def generate_reference_answer(self, *args, **kwargs):
            raise AIProviderError()

    _use_provider(monkeypatch, _Boom())

    resp = client.post(f"/api/questions/{question.id}/reference-answer", headers=hr_headers)

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_PROVIDER_ERROR"

    db.rollback()
    assert client.get(f"/api/questions/{question.id}", headers=hr_headers).json()[
        "reference_answer"
    ] is None


def test_generate_reference_answer_respects_isolation(client, hr_headers, db, other_position, other_hr):
    theirs = _seed(db, other_position, other_hr)

    resp = client.post(f"/api/questions/{theirs.id}/reference-answer", headers=hr_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_generate_reference_answer_nonexistent_question_is_404(client, hr_headers):
    resp = client.post("/api/questions/424242/reference-answer", headers=hr_headers)

    assert resp.status_code == 404


def test_generate_reference_answer_rejects_candidate(client, candidate_headers, db, position, hr_user):
    question = _seed(db, position, hr_user)

    resp = client.post(f"/api/questions/{question.id}/reference-answer", headers=candidate_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"
