"""evaluation service 层测试 —— 同步、无 SSE、无网络。

直接调用 evaluate_interview 并传入间谍回调，因此不涉及异步、HTTP 或 SSE。
"""

import pytest

from app.evaluation import repository
from app.evaluation import service as evaluation_service
from app.interview import service as interview_service
from app.interview.schemas import InterviewCreate

ANSWER = "我在上一家公司负责过一个高并发的订单系统重构项目，通过引入缓存与分库分表，" * 3


@pytest.fixture
def completed_interview(db, hr_user, position):
    """一个已完成、且逐题都有回答的面试。"""
    detail = interview_service.create_interview(
        db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
    )

    for question in detail.questions:
        interview_service.save_answer(
            db, hr_user, detail.id, question.interview_question_id, ANSWER
        )

    interview_service.complete_interview(db, hr_user, detail.id)
    return detail


@pytest.fixture
def spy():
    """记录全部 on_event 调用的间谍。"""

    class Spy:
        def __init__(self):
            self.events = []

        def __call__(self, event):
            self.events.append(event)

        @property
        def names(self):
            return [e.name for e in self.events]

        def payloads(self, name):
            return [e.payload for e in self.events if e.name == name]

    return Spy()


# ---------------------------- 阶段与落库 ----------------------------


class TestEvaluationPipeline:
    def test_writes_question_scores(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        assert len(repository.list_question_scores(db, completed_interview.id)) == 8

    def test_writes_dimension_scores(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        scores = repository.list_dimension_scores(db, completed_interview.id)
        assert len(scores) == 3  # 岗位定义了 3 个维度

    def test_writes_report(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        report = repository.get_report(db, completed_interview.id)

        assert report is not None
        assert report.conclusion
        assert report.strengths
        assert report.weaknesses

    def test_overall_score_in_range(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        assert 0.0 <= float(repository.get_report(db, completed_interview.id).overall_score) <= 10.0

    def test_all_scores_in_range(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        for score in repository.list_question_scores(db, completed_interview.id):
            assert 0.0 <= float(score.score) <= 10.0
        for score in repository.list_dimension_scores(db, completed_interview.id):
            assert 0.0 <= float(score.score) <= 10.0

    def test_scores_have_one_decimal(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        for score in repository.list_question_scores(db, completed_interview.id):
            assert round(float(score.score), 1) == float(score.score)

    def test_status_becomes_evaluated(self, db, completed_interview, spy):
        from app.interview import repository as interview_repo

        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        assert interview_repo.get_by_id(db, completed_interview.id).status == "evaluated"


# ---------------------------- 事件契约 ----------------------------


class TestEventContract:
    def test_events_order(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        names = spy.names
        assert names == ["question"] * 8 + ["dimension"] * 3 + ["report"]

    def test_question_events_ordered_by_seq(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        seqs = [p["seq"] for p in spy.payloads("question")]
        assert seqs == sorted(seqs) == list(range(1, 9))

    def test_question_event_fields(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        payload = spy.payloads("question")[0]

        for field in ("interview_question_id", "seq", "index", "total", "dimension", "score", "comment"):
            assert field in payload
        assert payload["total"] == 8
        assert payload["index"] == 1

    def test_dimension_event_fields(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        payload = spy.payloads("dimension")[0]

        for field in ("dimension", "index", "total", "score", "comment"):
            assert field in payload
        assert payload["total"] == 3

    def test_report_event_fields(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        payload = spy.payloads("report")[0]

        assert set(payload) == {
            "overall_score",
            "conclusion",
            "strengths",
            "weaknesses",
        }

    def test_dimension_events_cover_all_dims(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        dims = {p["dimension"] for p in spy.payloads("dimension")}
        assert dims == set(completed_interview.evaluation_dimensions)


# ---------------------------- 状态前置条件 ----------------------------


class TestPreconditions:
    def test_from_completed_ok(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)

    def test_from_ongoing_rejected(self, db, hr_user, position, spy):
        from app.core.exceptions import BusinessError

        detail = interview_service.create_interview(
            db, hr_user, InterviewCreate(position_id=position.id, candidate_name="李四")
        )
        with pytest.raises(BusinessError):
            evaluation_service.evaluate_interview(db, detail.id, spy)

    def test_reevaluate_replaces_scores(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        first_count = len(repository.list_question_scores(db, completed_interview.id))

        # 回到可评估状态后重评
        interview_service.transition_to_evaluating(db, completed_interview.id)
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        assert len(repository.list_question_scores(db, completed_interview.id)) == first_count

    def test_reevaluate_updates_report(self, db, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        first = repository.get_report(db, completed_interview.id)

        interview_service.transition_to_evaluating(db, completed_interview.id)
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        assert repository.get_report(db, completed_interview.id).id == first.id
        assert repository.get_report(db, completed_interview.id).updated_at >= first.created_at


# ---------------------------- 失败处理 ----------------------------


class FailingProvider:
    """所有方法都失败 —— 用于验证失败路径。"""

    def generate_questions(self, *args, **kwargs):
        raise AssertionError("不应调用出题")  # pragma: no cover

    def evaluate_answer(self, *args, **kwargs):
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")

    def evaluate_dimensions(self, *args, **kwargs):  # pragma: no cover
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")

    def summarize_report(self, *args, **kwargs):  # pragma: no cover
        from app.core.exceptions import AIProviderError

        raise AIProviderError("模拟评估失败")


class TestFailureHandling:
    def test_ai_failure_leaves_db_unchanged(
        self, db, completed_interview, spy, monkeypatch
    ):
        from app.core.exceptions import AIProviderError

        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )

        with pytest.raises(AIProviderError):
            evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        db.rollback()
        assert repository.list_question_scores(db, completed_interview.id) == []
        assert repository.list_dimension_scores(db, completed_interview.id) == []
        assert repository.get_report(db, completed_interview.id) is None

    def test_ai_failure_preserves_previous_result(
        self, db, completed_interview, spy, monkeypatch
    ):
        """先成功评估一次，再让重评失败 —— 旧结果必须完好无损。"""
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        old_report = repository.get_report(db, completed_interview.id)
        old_scores = repository.list_question_scores(db, completed_interview.id)

        interview_service.transition_to_evaluating(db, completed_interview.id)
        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: FailingProvider()
        )

        from app.core.exceptions import AIProviderError

        with pytest.raises(AIProviderError):
            evaluation_service.evaluate_interview(db, completed_interview.id, spy)

        db.rollback()
        assert repository.get_report(db, completed_interview.id).id == old_report.id
        assert len(repository.list_question_scores(db, completed_interview.id)) == len(
            old_scores
        )


# ---------------------------- 报告读取 ----------------------------


class TestGetReport:
    def test_report_ok(self, db, hr_user, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        report = evaluation_service.get_report(db, hr_user, completed_interview.id)

        assert report.overall_score >= 0
        assert report.conclusion
        assert report.strengths
        assert report.weaknesses
        assert report.candidate_name == "张三"

    def test_report_includes_all_dimensions(self, db, hr_user, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        report = evaluation_service.get_report(db, hr_user, completed_interview.id)

        assert {d.dimension for d in report.dimension_scores} == set(
            completed_interview.evaluation_dimensions
        )

    def test_report_question_scores_ordered_by_seq(
        self, db, hr_user, completed_interview, spy
    ):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        report = evaluation_service.get_report(db, hr_user, completed_interview.id)

        seqs = [q.seq for q in report.question_scores]
        assert seqs == sorted(seqs) == list(range(1, 9))

    def test_report_includes_question_details(self, db, hr_user, completed_interview, spy):
        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        report = evaluation_service.get_report(db, hr_user, completed_interview.id)

        first = report.question_scores[0]
        assert first.content
        assert first.dimension
        assert first.answer == ANSWER
        assert first.comment

    def test_report_before_evaluation_returns_409(self, db, hr_user, completed_interview):
        from app.core.exceptions import BusinessError

        with pytest.raises(BusinessError):
            evaluation_service.get_report(db, hr_user, completed_interview.id)

    def test_report_when_ongoing_returns_409(self, db, hr_user, position):
        from app.core.exceptions import BusinessError

        detail = interview_service.create_interview(
            db, hr_user, InterviewCreate(position_id=position.id, candidate_name="王五")
        )
        with pytest.raises(BusinessError):
            evaluation_service.get_report(db, hr_user, detail.id)

    def test_report_other_user_forbidden(self, db, other_hr, completed_interview, spy):
        from app.core.exceptions import ForbiddenError

        evaluation_service.evaluate_interview(db, completed_interview.id, spy)
        with pytest.raises(ForbiddenError):
            evaluation_service.get_report(db, other_hr, completed_interview.id)


def test_delete_all_for_interview(db, completed_interview, spy):
    evaluation_service.evaluate_interview(db, completed_interview.id, spy)
    repository.delete_all_for_interview(db, completed_interview.id)
    db.commit()

    assert repository.list_question_scores(db, completed_interview.id) == []
    assert repository.get_report(db, completed_interview.id) is None
