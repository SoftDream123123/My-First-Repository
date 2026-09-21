"""候选人脱敏反馈测试（计划书 module-14 §7.1–§7.5）。

本文件最重要的一组是 §7.1：脱敏规则的落点是**响应结构**，不是前端是否渲染。
"""

import re

import pytest
from sqlalchemy.exc import IntegrityError

from app.ai.base import CandidateFeedbackResult, DimensionScoreResult
from app.ai.mock_provider import MockProvider
from app.core.config import Settings, get_settings
from app.core.exceptions import AIProviderError
from app.evaluation import repository as evaluation_repository
from app.evaluation import service as evaluation_service
from app.interview import repository as interview_repository
from app.interview.models import STATUS_COMPLETED, STATUS_EVALUATED, STATUS_ONGOING

FEEDBACK_KEYS = {
    "interview_id",
    "level",
    "conclusion",
    "strengths",
    "weaknesses",
    "overall_score",
    "generated_at",
}


def _fresh(db) -> None:
    db.rollback()


def _url(interview_id: int) -> str:
    return f"/api/candidate/interviews/{interview_id}/feedback"


@pytest.fixture
def evaluated_interview(db, client, hr_headers, accepted_interview):
    """已接受邀请 + 面试完成 + 评估完成 —— 可读反馈的完整前置。"""
    interview_id = accepted_interview["interview_id"]

    assert (
        client.post(
            f"/api/interviews/{interview_id}/complete", headers=hr_headers
        ).status_code
        == 200
    )

    _fresh(db)
    evaluation_service.evaluate_interview(db, interview_id, lambda event: None)

    _fresh(db)
    assert (
        interview_repository.get_by_id(db, interview_id).status == STATUS_EVALUATED
    )
    return {**accepted_interview, "report": evaluation_repository.get_report(db, interview_id)}


class _SpyFeedbackProvider(MockProvider):
    """只覆盖 feedback 方法的 provider。

    继承 MockProvider 而非裸类：`get_provider` 是全局补丁，同一个 provider 也会被
    `evaluate_interview` 用到（重新评估的用例），因此其余六个方法必须可用。
    """

    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def generate_candidate_feedback(
        self, level, overall_score, strengths, weaknesses, dimension_scores
    ):
        self.calls.append(
            (level, overall_score, strengths, weaknesses, dimension_scores)
        )
        if self._error is not None:
            raise self._error
        return self._result or CandidateFeedbackResult(
            conclusion=f"脱敏后的结论（{level}）",
            strengths=list(strengths),
            weaknesses=list(weaknesses),
            overall_score=overall_score if level == "full" else None,
        )


def _use_provider(monkeypatch, provider) -> None:
    monkeypatch.setattr("app.evaluation.service.get_provider", lambda: provider)


def _set_level(monkeypatch, level: str) -> None:
    monkeypatch.setenv("CANDIDATE_FEEDBACK_LEVEL", level)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _restore_settings():
    yield
    get_settings.cache_clear()


# ==================== 7.1 脱敏（最重要） ====================


class TestSanitization:
    def test_summary_response_keys_exactly_match_whitelist(
        self, client, candidate_headers, evaluated_interview
    ):
        """键集合**精确等于**白名单七项。

        用「精确比对」而非「包含比对」：只断言 overall_score 为 None 无法发现
        「逐题分被顺手带出去了」。
        """
        body = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).json()
        assert set(body) == FEEDBACK_KEYS

    def test_summary_has_no_overall_score(
        self, client, candidate_headers, evaluated_interview
    ):
        body = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).json()
        assert body["level"] == "summary"
        assert body["overall_score"] is None

    @pytest.mark.parametrize(
        "forbidden",
        ["question_scores", "dimension_scores", "radar", "evaluated_at", "position_name"],
    )
    def test_response_never_contains_detail(
        self, client, candidate_headers, evaluated_interview, forbidden
    ):
        """原始 JSON 文本里不出现任何明细 / HR 侧字段名。"""
        raw = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).text
        assert forbidden not in raw

    def test_strengths_entries_carry_no_dimension_score(
        self, client, candidate_headers, evaluated_interview
    ):
        """优缺点条目里不得出现维度分。

        这两组条目是**原样**从 HR 报告透传的（PRD §4.9「便于两处逐条对照」），
        因此报告条目若内嵌「沟通能力（7.0）」，就等于绕过脱敏把维度分发给候选人。
        分数只能出现在 HR 侧的 `dimension_scores` 里。
        """
        body = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).json()

        entries = body["strengths"] + body["weaknesses"]
        assert entries, "本用例需要一个非空的优缺点列表才有意义"
        for entry in entries:
            assert not re.search(r"[0-9]", entry), entry

    def test_no_per_question_score_keys(
        self, client, candidate_headers, evaluated_interview
    ):
        """不存在表示「逐题分」的键。

        ⚠️ 不能用子串匹配 `'score' not in raw` —— `score` 也是白名单字段
        `overall_score` 的一部分，那样断言必然失败且误导。要比对的是**键**。
        """
        body = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).json()
        assert "score" not in body
        assert "comment" not in body
        assert set(body) - FEEDBACK_KEYS == set()  # 无白名单之外的键

    def test_full_has_overall_score_but_still_no_detail(
        self, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        _set_level(monkeypatch, "full")

        resp = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        )
        body = resp.json()
        assert body["level"] == "full"
        assert body["overall_score"] is not None
        # 即使 full 档，逐题分与维度分仍然不出现
        assert "question_scores" not in resp.text
        assert "dimension_scores" not in resp.text

    def test_client_cannot_escalate_level(
        self, client, candidate_headers, evaluated_interview
    ):
        """客户端传 ?level=full 被忽略 —— 档位只来自服务端配置。"""
        body = client.get(
            _url(evaluated_interview["interview_id"]),
            params={"level": "full"},
            headers=candidate_headers,
        ).json()
        assert body["level"] == "summary"
        assert body["overall_score"] is None


# ==================== 7.2 可见性与状态 ====================


class TestVisibility:
    def test_requires_accepted_invitation(
        self, client, db, hr_headers, candidate_headers, position, evaluated_interview
    ):
        """未接受邀请 → 403。"""
        pending = client.post(
            "/api/interviews",
            json={"position_id": position.id, "candidate_name": "未被邀请者"},
            headers=hr_headers,
        ).json()
        client.post(
            f"/api/interviews/{pending['id']}/invitations", headers=hr_headers
        )

        assert (
            client.get(_url(pending["id"]), headers=candidate_headers).status_code == 403
        )

    def test_after_invitation_revoked_forbidden(
        self, client, hr_headers, candidate_headers, evaluated_interview
    ):
        """接受后被撤销 → 403（复用 interview 的可见性判据）。"""
        interview_id = evaluated_interview["interview_id"]
        assert (
            client.get(_url(interview_id), headers=candidate_headers).status_code == 200
        )

        client.delete(
            f"/api/interviews/{interview_id}/invitations/"
            f"{evaluated_interview['invitation_id']}",
            headers=hr_headers,
        )

        assert (
            client.get(_url(interview_id), headers=candidate_headers).status_code == 403
        )

    def test_other_candidates_interview_forbidden(
        self, client, other_candidate_headers, evaluated_interview
    ):
        assert (
            client.get(
                _url(evaluated_interview["interview_id"]),
                headers=other_candidate_headers,
            ).status_code
            == 403
        )

    @pytest.mark.parametrize("status", [STATUS_ONGOING, STATUS_COMPLETED])
    def test_before_evaluation_conflict(
        self, client, db, hr_headers, candidate_headers, accepted_interview, status
    ):
        """非 evaluated → 409「评估尚未完成」。"""
        interview_id = accepted_interview["interview_id"]

        _fresh(db)
        interview = interview_repository.get_by_id(db, interview_id)
        interview.status = status
        db.commit()

        resp = client.get(_url(interview_id), headers=candidate_headers)
        assert resp.status_code == 409
        assert resp.json()["message"] == "评估尚未完成"

    def test_only_after_evaluated(self, client, candidate_headers, evaluated_interview):
        resp = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        )
        assert resp.status_code == 200

    def test_rejects_hr_and_admin(
        self, client, hr_headers, admin_headers, evaluated_interview
    ):
        url = _url(evaluated_interview["interview_id"])
        assert client.get(url, headers=hr_headers).status_code == 403
        assert client.get(url, headers=admin_headers).status_code == 403

    def test_rejects_anonymous(self, client, evaluated_interview):
        assert client.get(_url(evaluated_interview["interview_id"])).status_code == 401


# ==================== 7.3 生成、缓存与失效 ====================


class TestGenerationAndCache:
    def test_first_read_generates_and_caches(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        spy = _SpyFeedbackProvider()
        _use_provider(monkeypatch, spy)

        interview_id = evaluated_interview["interview_id"]
        assert client.get(_url(interview_id), headers=candidate_headers).status_code == 200

        assert len(spy.calls) == 1
        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is not None

    def test_second_read_uses_cache(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        """二次读取**不再调用** provider，内容与首次一致。"""
        spy = _SpyFeedbackProvider()
        _use_provider(monkeypatch, spy)

        interview_id = evaluated_interview["interview_id"]
        first = client.get(_url(interview_id), headers=candidate_headers).json()
        second = client.get(_url(interview_id), headers=candidate_headers).json()

        assert len(spy.calls) == 1  # 只调了一次
        assert first["conclusion"] == second["conclusion"]

    def test_cache_content_is_level_independent(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        """先 summary 生成，再切到 full → **不重新生成**，仅总分变为非空。"""
        spy = _SpyFeedbackProvider()
        _use_provider(monkeypatch, spy)

        interview_id = evaluated_interview["interview_id"]
        summary = client.get(_url(interview_id), headers=candidate_headers).json()
        assert summary["overall_score"] is None

        _set_level(monkeypatch, "full")
        full = client.get(_url(interview_id), headers=candidate_headers).json()

        assert len(spy.calls) == 1  # 没有重新生成
        assert full["overall_score"] is not None
        assert full["conclusion"] == summary["conclusion"]  # 文案没变

    def test_ai_receives_raw_values(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        spy = _SpyFeedbackProvider()
        _use_provider(monkeypatch, spy)

        client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        )

        level, overall_score, strengths, weaknesses, dimension_scores = spy.calls[0]
        assert isinstance(level, str)
        assert isinstance(overall_score, float)
        assert isinstance(strengths, list) and all(isinstance(s, str) for s in strengths)
        assert isinstance(weaknesses, list)
        # 维度得分是 ai 层的 dataclass —— 不是 ORM 行（ORM 行带 interview_id）
        assert dimension_scores
        assert all(isinstance(item, DimensionScoreResult) for item in dimension_scores)
        assert not hasattr(dimension_scores[0], "interview_id")
        # 报告那句结论**不在入参里**：它含招聘方的去留判断（PRD §4.9）

    def test_generation_failure_returns_502_and_no_row(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        _use_provider(
            monkeypatch, _SpyFeedbackProvider(error=AIProviderError("模拟失败"))
        )

        interview_id = evaluated_interview["interview_id"]
        resp = client.get(_url(interview_id), headers=candidate_headers)

        assert resp.status_code == 502
        assert resp.json()["code"] == "AI_PROVIDER_ERROR"

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is None

    def test_generation_failure_is_retryable(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        interview_id = evaluated_interview["interview_id"]

        _use_provider(
            monkeypatch, _SpyFeedbackProvider(error=AIProviderError("模拟失败"))
        )
        assert client.get(_url(interview_id), headers=candidate_headers).status_code == 502

        # provider 恢复后再次读取 → 200 且落库
        _use_provider(monkeypatch, _SpyFeedbackProvider())
        assert client.get(_url(interview_id), headers=candidate_headers).status_code == 200

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is not None

    def test_generation_does_not_break_hr_report(
        self, client, hr_headers, candidate_headers, evaluated_interview, monkeypatch
    ):
        """反馈生成失败**不影响** HR 侧报告。"""
        interview_id = evaluated_interview["interview_id"]

        _use_provider(
            monkeypatch, _SpyFeedbackProvider(error=AIProviderError("模拟失败"))
        )
        assert client.get(_url(interview_id), headers=candidate_headers).status_code == 502

        report = client.get(
            f"/api/interviews/{interview_id}/report", headers=hr_headers
        )
        assert report.status_code == 200
        assert report.json()["conclusion"]

    def test_reevaluation_invalidates_cache(
        self, db, client, hr_headers, candidate_headers, evaluated_interview, monkeypatch
    ):
        """重新评估后缓存行被删除。"""
        _use_provider(monkeypatch, _SpyFeedbackProvider())
        interview_id = evaluated_interview["interview_id"]
        client.get(_url(interview_id), headers=candidate_headers)

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is not None

        # 重新评估：回退到 completed 后再评估
        client.post(f"/api/interviews/{interview_id}/rollback", headers=hr_headers)
        client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)
        _fresh(db)
        evaluation_service.evaluate_interview(db, interview_id, lambda event: None)

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is None

    def test_feedback_after_reevaluation_is_regenerated(
        self, db, client, hr_headers, candidate_headers, evaluated_interview, monkeypatch
    ):
        spy = _SpyFeedbackProvider()
        _use_provider(monkeypatch, spy)
        interview_id = evaluated_interview["interview_id"]

        client.get(_url(interview_id), headers=candidate_headers)
        assert len(spy.calls) == 1

        client.post(f"/api/interviews/{interview_id}/rollback", headers=hr_headers)
        client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)
        _fresh(db)
        evaluation_service.evaluate_interview(db, interview_id, lambda event: None)

        resp = client.get(_url(interview_id), headers=candidate_headers)
        assert resp.status_code == 200
        assert len(spy.calls) == 2  # 重新生成了

    def test_failed_evaluation_keeps_cache(
        self, db, client, hr_headers, candidate_headers, evaluated_interview, monkeypatch
    ):
        """评估**失败**时缓存保留 —— 报告未被替换，反馈仍有效。"""
        _use_provider(monkeypatch, _SpyFeedbackProvider())
        interview_id = evaluated_interview["interview_id"]
        client.get(_url(interview_id), headers=candidate_headers)

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is not None

        # 让重新评估在第一阶段就失败
        class _FailingEvaluate:
            def evaluate_answer(self, *args, **kwargs):
                raise AIProviderError("模拟评估失败")

        monkeypatch.setattr(
            "app.evaluation.service.get_provider", lambda: _FailingEvaluate()
        )
        client.post(f"/api/interviews/{interview_id}/rollback", headers=hr_headers)
        client.post(f"/api/interviews/{interview_id}/complete", headers=hr_headers)

        _fresh(db)
        with pytest.raises(AIProviderError):
            evaluation_service.evaluate_interview(db, interview_id, lambda e: None)

        _fresh(db)
        assert evaluation_repository.get_candidate_feedback(db, interview_id) is not None

    def test_second_read_only_one_row(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        _use_provider(monkeypatch, _SpyFeedbackProvider())
        interview_id = evaluated_interview["interview_id"]

        for _ in range(3):
            assert (
                client.get(_url(interview_id), headers=candidate_headers).status_code
                == 200
            )

        _fresh(db)
        from sqlalchemy import func, select

        from app.evaluation.models import CandidateFeedback

        count = db.execute(
            select(func.count(CandidateFeedback.id)).where(
                CandidateFeedback.interview_id == interview_id
            )
        ).scalar_one()
        assert count == 1

    def test_concurrent_insert_recovers(
        self, db, client, candidate_headers, evaluated_interview, monkeypatch
    ):
        """并发首次读取撞唯一索引 → 读取既有行返回 200，而不是报错。

        直接构造那一幕：让缓存检查认为「没有缓存」（陈旧读），同时让写入撞唯一索引。
        """
        interview_id = evaluated_interview["interview_id"]

        # 先正常生成一行，代表「另一个请求已经写入」
        _use_provider(monkeypatch, _SpyFeedbackProvider())
        client.get(_url(interview_id), headers=candidate_headers)

        real_get = evaluation_repository.get_candidate_feedback
        state = {"first": True}

        def stale_get(db_, iid):
            if state["first"]:
                state["first"] = False
                return None  # 陈旧读：看不到另一请求刚提交的行
            return real_get(db_, iid)

        def conflicting_upsert(db_, iid, data):
            raise IntegrityError("duplicate", None, Exception("uq conflict"))

        monkeypatch.setattr(
            evaluation_repository, "get_candidate_feedback", stale_get
        )
        monkeypatch.setattr(
            evaluation_repository, "upsert_candidate_feedback", conflicting_upsert
        )

        resp = client.get(_url(interview_id), headers=candidate_headers)
        assert resp.status_code == 200
        assert resp.json()["conclusion"]


# ==================== 7.4 HR 侧零回归 ====================


class TestHrSideUnchanged:
    def test_hr_report_unchanged(self, client, hr_headers, evaluated_interview):
        """HR 报告的字段与 MVP-1 完全一致（不因新表而增减）。"""
        report = client.get(
            f"/api/interviews/{evaluated_interview['interview_id']}/report",
            headers=hr_headers,
        ).json()

        assert set(report) == {
            "interview_id",
            "candidate_name",
            "position_name",
            "overall_score",
            "conclusion",
            "strengths",
            "weaknesses",
            "evaluated_at",
            "dimension_scores",
            "question_scores",
        }

    def test_hr_report_never_contains_candidate_fields(
        self, client, hr_headers, evaluated_interview
    ):
        raw = client.get(
            f"/api/interviews/{evaluated_interview['interview_id']}/report",
            headers=hr_headers,
        ).text
        assert "candidate_feedback" not in raw
        assert "generated_at" not in raw

    def test_report_has_no_dimension_leak_to_candidate(
        self, client, candidate_headers, evaluated_interview
    ):
        """反向：候选人响应里也不出现 HR 报告的字段名。"""
        raw = client.get(
            _url(evaluated_interview["interview_id"]), headers=candidate_headers
        ).text
        assert "candidate_name" not in raw
        assert "position_name" not in raw
        assert "evaluated_at" not in raw


# ==================== 7.5 配置校验 ====================


class TestConfig:
    def test_default_level_is_summary(self, monkeypatch):
        monkeypatch.delenv("CANDIDATE_FEEDBACK_LEVEL", raising=False)
        assert Settings.model_fields["candidate_feedback_level"].default == "summary"

    def test_invalid_level_fails_fast(self):
        """非法档位 → 启动期报错（fail fast），而不是静默降级。"""
        with pytest.raises(Exception) as exc:
            Settings(candidate_feedback_level="detailed")
        assert "CANDIDATE_FEEDBACK_LEVEL" in str(exc.value)

    @pytest.mark.parametrize("level", ["summary", "full"])
    def test_valid_levels_accepted(self, level):
        assert Settings(candidate_feedback_level=level).candidate_feedback_level == level
