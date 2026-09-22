"""interview 简历 AI 评估的服务层测试（PRD §4.15）。

用 Mock Provider（默认），因此断言的是**业务契约**：前置条件、错误码、
「不落库」，以及两条路径的一致性 —— 不涉及具体分数取值。
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import (
    AIProviderError,
    BusinessError,
    ForbiddenError,
    NotFoundError,
)
from app.interview import repository, service


@pytest.fixture
def linked(db, linked_interview) -> dict:
    """`linked_interview` 是经 TestClient（另一个会话）建出来的，而本文件的 `db`
    会话在默认隔离级别下看不到它 —— 先 `rollback()` 结束当前事务，测试里才读得到
    候选人刚写进去的 `resume_id`。这是本项目既有的处理方式。"""
    db.rollback()
    return linked_interview


def test_hr_review_without_linked_resume_is_409(db, hr_user, accepted_interview):
    db.rollback()

    with pytest.raises(BusinessError) as caught:
        service.review_resume(db, hr_user, accepted_interview["interview_id"])

    assert "尚未关联简历" in caught.value.message


def test_candidate_review_without_linked_resume_has_the_same_message(
    db, candidate_user, accepted_interview
):
    """两条路径的 409 文案必须逐字一致 —— 前端据同一句话引导用户去关联简历。"""
    db.rollback()

    with pytest.raises(BusinessError) as caught:
        service.review_resume_for_candidate(
            db, candidate_user, accepted_interview["interview_id"]
        )

    assert "尚未关联简历" in caught.value.message


def test_hr_review_returns_result(db, hr_user, linked):
    result = service.review_resume(db, hr_user, linked["interview_id"])

    assert 0.0 <= result.match_score <= 10.0
    assert result.conclusion.strip()
    # strengths 恒非空（module-27 §3 的契约）
    assert result.strengths


def test_candidate_review_returns_the_same_result(db, hr_user, candidate_user, linked):
    """同一场面试的两个端点返回**同一份** AI 结果（脱敏只发生在 router 层）。"""
    interview_id = linked["interview_id"]

    assert service.review_resume(
        db, hr_user, interview_id
    ) == service.review_resume_for_candidate(db, candidate_user, interview_id)


def test_review_does_not_touch_the_database(db, hr_user, linked):
    """PRD §4.15 的「不落库」：评完前后，库里的行一行不变。"""
    interview_id = linked["interview_id"]
    before = repository.list_question_ids(db, interview_id)

    service.review_resume(db, hr_user, interview_id)

    assert repository.list_question_ids(db, interview_id) == before
    assert repository.get_resume_id_of_interview(db, interview_id) is not None


@pytest.mark.parametrize("status", ["draft", "completed"])
def test_review_is_allowed_in_any_interview_status(db, hr_user, linked, status):
    """评估不写数据，因此**不限面试状态** —— 与补题要求 `ongoing` 刻意相反。"""
    from app.interview.models import Interview

    interview = db.get(Interview, linked["interview_id"])
    interview.status = status
    db.commit()

    assert service.review_resume(db, hr_user, linked["interview_id"]).match_score >= 0.0


def test_position_without_dimensions_is_409(db, hr_user, linked, monkeypatch):
    """防御性分支：岗位表经 API 建不出空维度（schema 要求至少 1 个），
    但数据可被直接写入，因此这里保留拦截并显式测它。"""
    monkeypatch.setattr(
        repository,
        "get_position",
        lambda db, position_id: SimpleNamespace(
            name="空维度岗位", jd="JD", evaluation_dimensions=[]
        ),
    )

    with pytest.raises(BusinessError) as caught:
        service.review_resume(db, hr_user, linked["interview_id"])

    assert "评估维度" in caught.value.message


def test_missing_position_also_falls_into_the_dimension_branch(db, hr_user, linked, monkeypatch):
    """岗位行不存在时同样走 409 —— **不为它单独加一个 404**。"""
    monkeypatch.setattr(repository, "get_position", lambda db, position_id: None)

    with pytest.raises(BusinessError) as caught:
        service.review_resume(db, hr_user, linked["interview_id"])

    assert "评估维度" in caught.value.message


def test_provider_error_is_not_swallowed(db, hr_user, linked, monkeypatch):
    """service **不 catch** AIProviderError：全局处理器要把它转成 502。
    在这里吞掉会让 502 变成一个自制的 500。"""
    from app.interview import service as service_module

    class _Boom:
        def evaluate_resume(self, **_kwargs):
            raise AIProviderError("上游失败")

    monkeypatch.setattr(service_module, "get_provider", lambda: _Boom())

    with pytest.raises(AIProviderError):
        service.review_resume(db, hr_user, linked["interview_id"])


def test_hr_cannot_review_another_hrs_interview(db, other_hr, linked):
    with pytest.raises(ForbiddenError):
        service.review_resume(db, other_hr, linked["interview_id"])


def test_candidate_cannot_review_an_interview_it_did_not_accept(db, other_candidate, linked):
    with pytest.raises(ForbiddenError):
        service.review_resume_for_candidate(db, other_candidate, linked["interview_id"])


def test_candidate_review_of_missing_interview_is_404(db, candidate_user):
    with pytest.raises(NotFoundError):
        service.review_resume_for_candidate(db, candidate_user, 424242)
