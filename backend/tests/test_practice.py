"""practice 模块 service / repository 测试（计划书 module-13 §7.1–§7.4）。

关键点：单选不调 AI、空作答不调 AI、无参考答案不调 AI、AI 失败降级为未判分、
计数用重算而非累加、错题本排除未判分、正确率分母是已判分数。
"""

import pytest

from app.ai.base import MatchedQuestion, PracticeGradeResult
from app.ai.mock_provider import MockProvider
from app.core.config import get_settings
from app.core.exceptions import (
    AIProviderError,
    BusinessError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.practice import repository, service as practice_service
from app.practice.models import (
    STATUS_FINISHED,
    STATUS_ONGOING,
    PracticeSession,
)
from app.practice.schemas import PracticeItemSubmit, PracticeSessionCreate
from app.question import repository as question_repository
from app.question.schemas import PracticeFilters


# ------------------------------ 测试替身 ------------------------------


class SpyProvider:
    """记录调用参数的 provider。"""

    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def grade_practice_answer(
        self, question_type, content, reference_answer, user_answer
    ):
        self.calls.append((question_type, content, reference_answer, user_answer))
        if self._error is not None:
            raise self._error
        return self._result or PracticeGradeResult(
            score=8.0, is_correct=True, explanation="spy 判分结果"
        )


class ExplodingProvider:
    """被调用即失败 —— 用于断言「不应调用 AI」。"""

    def grade_practice_answer(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("本分支不应调用 AI Provider")


def _use_provider(monkeypatch, provider) -> None:
    monkeypatch.setattr(
        "app.practice.service.get_provider", lambda: provider
    )


def _by_type(detail, question_type: str):
    return next(
        item for item in detail.items if item.question["question_type"] == question_type
    )


def _submit(db, user, session_id, item_id, answer):
    return practice_service.submit_item(
        db, user, session_id, PracticeItemSubmit(item_id=item_id, user_answer=answer)
    )


# ==================== 7.1 会话与取题 ====================


class TestStartSession:
    def test_writes_snapshots(self, db, candidate_user, practice_questions):
        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=4)
        )
        assert detail.session.total == 4

        for item in detail.items:
            source = question_repository.get_by_id(db, item.question["id"])
            assert item.question["content"] == source.content
            assert item.question["options"] == list(source.options or [])
            assert item.question["dimension"] == source.dimension
            assert item.question["question_type"] == source.question_type

        # 参考答案快照也写满（但**不下发**给候选人）
        stored = repository.list_items(db, detail.session.id)
        for entry, source in zip(
            stored, [q for q in practice_questions], strict=False
        ):
            assert entry.reference_answer_snapshot == source.reference_answer

    def test_default_size(self, db, candidate_user, hr_user, position):
        for index in range(12):
            question_repository.create(
                db,
                position_id=position.id,
                category="通用",
                dimension="沟通能力",
                content=f"第{index}道题的题干内容描述",
                difficulty="medium",
                tags=[],
                source="bank",
                question_type="short_answer",
                created_by=hr_user.id,
            )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate()
        )
        assert detail.session.total == get_settings().practice_session_size_default

    def test_size_capped(self, db, candidate_user, practice_questions):
        """超上限**报错**，不静默截断。"""
        with pytest.raises(ValidationError):
            practice_service.start_session(
                db, candidate_user, PracticeSessionCreate(size=999)
            )

    def test_insufficient_questions(self, db, candidate_user, practice_questions):
        """只有 4 题符合却要 10 题 → 按实际 4 题建会话，不报错。"""
        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=10)
        )
        assert detail.session.total == 4

    def test_no_questions_creates_no_session(self, db, candidate_user):
        before = db.query(PracticeSession).count()

        with pytest.raises(BusinessError):
            practice_service.start_session(
                db, candidate_user, PracticeSessionCreate()
            )

        assert db.query(PracticeSession).count() == before

    def test_filters_applied(self, db, candidate_user, practice_questions):
        detail = practice_service.start_session(
            db,
            candidate_user,
            PracticeSessionCreate(dimension="沟通能力", question_type="single_choice"),
        )
        assert detail.session.total == 2
        for item in detail.items:
            assert item.question["dimension"] == "沟通能力"
            assert item.question["question_type"] == "single_choice"

    def test_uses_other_hrs_questions(
        self, db, candidate_user, hr_user, other_hr, position, other_position
    ):
        """刷题取全库题目 —— 跨 HR 的题都能取到（module-10 §5.5 的有意放宽）。"""
        for owner, pos in ((hr_user, position), (other_hr, other_position)):
            question_repository.create(
                db,
                position_id=pos.id,
                category="通用",
                dimension="沟通能力",
                content=f"由用户{owner.id}创建的题目内容",
                difficulty="medium",
                tags=[],
                source="bank",
                question_type="short_answer",
                created_by=owner.id,
            )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=10)
        )
        assert detail.session.total == 2


# ==================== 7.2 判分分支 ====================


class TestGrading:
    def test_single_choice_correct(self, db, candidate_user, practice_session, monkeypatch):
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        source = question_repository.get_by_id(db, item.question["id"])

        result = _submit(db, candidate_user, practice_session.session.id, item.item_id, source.reference_answer)

        assert result.is_correct is True
        assert result.score == 10.0
        assert result.correct_answer == source.reference_answer

    def test_single_choice_wrong(self, db, candidate_user, practice_session, monkeypatch):
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")

        result = _submit(
            db, candidate_user, practice_session.session.id, item.item_id, "肯定不是答案的选项"
        )
        assert result.is_correct is False
        assert result.score == 0.0

    def test_single_choice_ignores_whitespace(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        source = question_repository.get_by_id(db, item.question["id"])

        result = _submit(
            db,
            candidate_user,
            practice_session.session.id,
            item.item_id,
            f"  {source.reference_answer}  ",
        )
        assert result.is_correct is True

    def test_short_answer_calls_ai_with_raw_values(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        spy = SpyProvider()
        _use_provider(monkeypatch, spy)
        item = _by_type(practice_session, "short_answer")

        _submit(db, candidate_user, practice_session.session.id, item.item_id, "我的作答内容")

        assert len(spy.calls) == 1
        question_type, content, reference, user_answer = spy.calls[0]
        assert isinstance(question_type, str)
        assert isinstance(content, str)
        assert isinstance(reference, str)
        assert user_answer == "我的作答内容"
        # 不是 ORM 对象
        assert not hasattr(content, "created_by")

    def test_short_answer_uses_ai_result(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        _use_provider(
            monkeypatch,
            SpyProvider(
                result=PracticeGradeResult(
                    score=7.5, is_correct=True, explanation="AI 给出的解析"
                )
            ),
        )
        item = _by_type(practice_session, "short_answer")

        result = _submit(db, candidate_user, practice_session.session.id, item.item_id, "作答")
        assert result.is_correct is True
        assert result.score == 7.5
        assert result.explanation == "AI 给出的解析"

    def test_short_answer_no_reference_is_unscored(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        """简答且无参考答案 → 未判分，且**不调用 AI**。"""
        _use_provider(monkeypatch, ExplodingProvider())
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="这道简答题没有参考答案内容",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        item = detail.items[0]
        result = _submit(db, candidate_user, detail.session.id, item.item_id, "我的作答")

        assert result.is_correct is None
        assert result.score is None
        assert "暂无参考答案" in result.explanation

    def test_empty_answer_zero_and_no_ai(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "short_answer")

        result = _submit(db, candidate_user, practice_session.session.id, item.item_id, "   ")
        assert result.is_correct is False
        assert result.score == 0.0
        assert result.explanation == "未作答"

    def test_ai_failure_marks_unscored_and_keeps_answer(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        """AI 失败 → 200 语义（不抛错）、作答已落库、标记未判分。"""
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("模拟失败")))
        item = _by_type(practice_session, "short_answer")

        result = _submit(
            db, candidate_user, practice_session.session.id, item.item_id, "已保存的作答"
        )

        assert result.is_correct is None
        assert result.score is None
        assert "重判" in result.explanation

        stored = repository.get_item_by_id(db, item.item_id)
        assert stored.user_answer == "已保存的作答"  # 作答确实持久化了

    def test_backfills_reference_from_question(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        """会话建立时无参考答案 → HR 补录后提交 → 判分成功且快照被回填。"""
        question = question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="开始练习时还没有参考答案的题目",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        assert repository.get_item_by_id(db, detail.items[0].item_id).reference_answer_snapshot is None

        # HR 事后补录参考答案
        question_repository.update(
            db, question, reference_answer="事后补录的参考答案文本"
        )
        db.commit()

        _use_provider(monkeypatch, SpyProvider())
        result = _submit(
            db, candidate_user, detail.session.id, detail.items[0].item_id, "作答"
        )

        assert result.is_correct is True  # 判分成功，不再是未判分
        stored = repository.get_item_by_id(db, detail.items[0].item_id)
        assert stored.reference_answer_snapshot == "事后补录的参考答案文本"  # 回填了

    def test_keeps_existing_snapshot_over_question(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        """快照已有答案而题库答案后来被改 → 判分用**快照**。"""
        item = _by_type(practice_session, "short_answer")
        question = question_repository.get_by_id(db, item.question["id"])
        original_snapshot = repository.get_item_by_id(
            db, item.item_id
        ).reference_answer_snapshot

        question_repository.update(db, question, reference_answer="题库被改后的新答案")
        db.commit()

        spy = SpyProvider()
        _use_provider(monkeypatch, spy)
        _submit(db, candidate_user, practice_session.session.id, item.item_id, "作答")

        assert spy.calls[0][2] == original_snapshot  # 传给 AI 的是快照值

    def test_after_finish_rejected(self, db, candidate_user, practice_session):
        practice_service.finish_session(db, candidate_user, practice_session.session.id)
        item = practice_session.items[0]

        with pytest.raises(BusinessError):
            _submit(db, candidate_user, practice_session.session.id, item.item_id, "作答")

    def test_other_session_item_rejected(self, db, candidate_user, practice_session):
        with pytest.raises(Exception) as exc:
            _submit(db, candidate_user, practice_session.session.id, 999999, "作答")
        assert "不属于" in str(exc.value)

    def test_other_candidates_session_forbidden(
        self, db, other_candidate, practice_session
    ):
        from app.core.exceptions import ForbiddenError

        item = practice_session.items[0]
        with pytest.raises(ForbiddenError):
            _submit(db, other_candidate, practice_session.session.id, item.item_id, "作答")


# ================== 7.3 计数、错题本与统计 ==================


class TestRecount:
    def test_reanswer_does_not_double_count(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        """同一题提交两次（先错后对）→ answered=1、correct=1，不重复累加。"""
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        source = question_repository.get_by_id(db, item.question["id"])

        _submit(db, candidate_user, practice_session.session.id, item.item_id, "错误选项")
        _submit(
            db, candidate_user, practice_session.session.id, item.item_id, source.reference_answer
        )

        session = repository.get_session_by_id(db, practice_session.session.id)
        assert session.answered_count == 1
        assert session.correct_count == 1

    def test_counts_blank_answers(self, db, candidate_user, practice_session):
        item = practice_session.items[0]
        _submit(db, candidate_user, practice_session.session.id, item.item_id, "")

        session = repository.get_session_by_id(db, practice_session.session.id)
        assert session.answered_count == 1  # 空串是「提交了但未作答」，仍占位

    def test_excludes_unscored_from_correct(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="会被 AI 判分失败的简答题",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer="参考答案内容",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        _submit(db, candidate_user, detail.session.id, detail.items[0].item_id, "作答")

        session = repository.get_session_by_id(db, detail.session.id)
        assert session.answered_count == 1
        assert session.correct_count == 0  # 未判分不计入正确数


class TestWrongBook:
    def test_excludes_unscored(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        """未判分（is_correct IS NULL）**不出现**在错题本。"""
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="AI 判分失败的题目内容",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer="参考答案",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        _submit(db, candidate_user, detail.session.id, detail.items[0].item_id, "作答")

        assert practice_service.list_wrong_book(db, candidate_user, None, None, None, 50) == []

    def test_dedupes_by_question_with_count(
        self, db, candidate_user, practice_questions, monkeypatch
    ):
        """同一道题在 3 次练习里都判错 → 1 行，wrong_count == 3。

        ⚠️ 累计的是**跨会话**的次数：同一个待答项重复提交只是覆盖同一行，
        行数恒为 1。所以「练错多次」必须由多次练习产生。
        """
        _use_provider(monkeypatch, ExplodingProvider())
        single = next(
            q for q in practice_questions if q.question_type == "single_choice"
        )

        for _ in range(3):
            detail = practice_service.start_session(
                db,
                candidate_user,
                PracticeSessionCreate(question_type="single_choice", size=10),
            )
            item = next(i for i in detail.items if i.question["id"] == single.id)
            _submit(
                db, candidate_user, detail.session.id, item.item_id, "错误选项"
            )

        book = practice_service.list_wrong_book(db, candidate_user, None, None, None, 50)
        assert len(book) == 1
        assert book[0].question_id == single.id
        assert book[0].wrong_count == 3

    def test_isolated_by_candidate(
        self, db, candidate_user, other_candidate, practice_session, monkeypatch
    ):
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        _submit(db, candidate_user, practice_session.session.id, item.item_id, "错误选项")

        assert practice_service.list_wrong_book(db, other_candidate, None, None, None, 50) == []
        assert len(practice_service.list_wrong_book(db, candidate_user, None, None, None, 50)) == 1


class TestStats:
    def test_accuracy_denominator_is_scored(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        """答 3 题、2 题判分、其中 1 题对 → accuracy == 0.5（分母是 2 不是 3）。"""
        # 1 道单选（会判分）+ 2 道简答（一道 AI 失败→未判分，一道成功）
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="单选的题干内容描述",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="single_choice",
            options=["甲", "乙"],
            reference_answer="甲",
            created_by=hr_user.id,
        )
        for index in (1, 2):
            question_repository.create(
                db,
                position_id=position.id,
                category="通用",
                dimension="专业能力",
                content=f"第{index}道简答的题干内容",
                difficulty="medium",
                tags=[],
                source="bank",
                question_type="short_answer",
                reference_answer=f"第{index}道简答的参考答案",
                created_by=hr_user.id,
            )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=3)
        )

        # 单选判对
        single = _by_type(detail, "single_choice")
        _use_provider(monkeypatch, ExplodingProvider())
        _submit(db, candidate_user, detail.session.id, single.item_id, "甲")

        # 两道简答：一道成功判错、一道 AI 失败
        short_items = [
            item for item in detail.items if item.question["question_type"] == "short_answer"
        ]

        _use_provider(
            monkeypatch,
            SpyProvider(
                result=PracticeGradeResult(score=3.0, is_correct=False, explanation="不准")
            ),
        )
        _submit(db, candidate_user, detail.session.id, short_items[0].item_id, "作答一")

        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        _submit(db, candidate_user, detail.session.id, short_items[1].item_id, "作答二")

        stats = practice_service.get_stats(db, candidate_user)
        assert stats.total_answered == 3
        assert stats.scored_count == 2
        assert stats.unscored_count == 1
        assert stats.correct_count == 1
        assert stats.accuracy == 0.5  # 1 / 2，分母是已判分数

    def test_accuracy_null_when_nothing_scored(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="必定判分失败的简答题内容",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer="参考答案",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        _submit(db, candidate_user, detail.session.id, detail.items[0].item_id, "作答")

        stats = practice_service.get_stats(db, candidate_user)
        assert stats.scored_count == 0
        assert stats.accuracy is None  # 不出现除零

    def test_by_dimension_uses_snapshot(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        """题库维度改名后，统计仍按 dimension_snapshot 归集。"""
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        original_dimension = item.question["dimension"]

        question = question_repository.get_by_id(db, item.question["id"])
        question_repository.update(db, question, dimension="被改名后的维度")
        db.commit()

        source_answer = question_repository.get_by_id(db, item.question["id"]).options[0]
        _submit(
            db, candidate_user, practice_session.session.id, item.item_id, source_answer
        )

        stats = practice_service.get_stats(db, candidate_user)
        dimensions = [row.dimension for row in stats.by_dimension]
        assert original_dimension in dimensions
        assert "被改名后的维度" not in dimensions

    def test_isolated_by_candidate(
        self, db, candidate_user, other_candidate, practice_session
    ):
        assert practice_service.get_stats(db, other_candidate).total_answered == 0
        assert practice_service.get_stats(db, other_candidate).session_count == 0


# ============== 7.4 结束练习、重判、限流 ==============


class TestFinish:
    def test_sets_status_and_time(self, db, candidate_user, practice_session):
        summary = practice_service.finish_session(db, candidate_user, practice_session.session.id)
        assert summary.status == STATUS_FINISHED

        session = repository.get_session_by_id(db, practice_session.session.id)
        assert session.finished_at is not None

    def test_is_idempotent(self, db, candidate_user, practice_session):
        first = practice_service.finish_session(db, candidate_user, practice_session.session.id)
        session_after_first = repository.get_session_by_id(db, practice_session.session.id)
        finished_at = session_after_first.finished_at

        second = practice_service.finish_session(db, candidate_user, practice_session.session.id)

        assert second.status == STATUS_FINISHED
        assert (
            repository.get_session_by_id(db, practice_session.session.id).finished_at
            == finished_at
        )

    def test_allows_incomplete_session(self, db, candidate_user, practice_session):
        """只答了 1/4 题也允许结束 —— 否则候选人无法退出。"""
        item = practice_session.items[0]
        _submit(db, candidate_user, practice_session.session.id, item.item_id, "只答一题")

        summary = practice_service.finish_session(db, candidate_user, practice_session.session.id)
        assert summary.answered_count == 1
        assert summary.total == 4

    def test_reports_unscored_count(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="判分会失败的简答题内容",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer="参考答案",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        _submit(db, candidate_user, detail.session.id, detail.items[0].item_id, "作答")

        summary = practice_service.finish_session(db, candidate_user, detail.session.id)
        assert summary.unscored_count == 1


class TestRescore:
    def test_unscored_item(
        self, db, candidate_user, hr_user, position, monkeypatch
    ):
        """未判分项在 provider 恢复后重判成功，计数更新。"""
        _use_provider(monkeypatch, SpyProvider(error=AIProviderError("失败")))
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension="沟通能力",
            content="重判用例的简答题内容",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer="参考答案内容",
            created_by=hr_user.id,
        )
        db.commit()

        detail = practice_service.start_session(
            db, candidate_user, PracticeSessionCreate(size=1)
        )
        item_id = detail.items[0].item_id
        assert _submit(db, candidate_user, detail.session.id, item_id, "作答").is_correct is None

        _use_provider(monkeypatch, SpyProvider())
        result = practice_service.rescore_item(db, candidate_user, item_id)

        assert result.is_correct is True
        session = repository.get_session_by_id(db, detail.session.id)
        assert session.correct_count == 1

    def test_scored_item_is_idempotent(
        self, db, candidate_user, practice_session, monkeypatch
    ):
        """已判分项重判 → 返回既有结果，**未再次调用 provider**。"""
        _use_provider(monkeypatch, ExplodingProvider())
        item = _by_type(practice_session, "single_choice")
        source = question_repository.get_by_id(db, item.question["id"])
        _submit(
            db, candidate_user, practice_session.session.id, item.item_id, source.reference_answer
        )

        result = practice_service.rescore_item(db, candidate_user, item.item_id)
        assert result.is_correct is True

    def test_other_candidates_item_forbidden(
        self, db, other_candidate, practice_session
    ):
        from app.core.exceptions import ForbiddenError

        with pytest.raises(ForbiddenError):
            practice_service.rescore_item(db, other_candidate, practice_session.items[0].item_id)


class TestRateLimit:
    def test_rejects_after_threshold(
        self, db, candidate_user, practice_questions, monkeypatch
    ):
        monkeypatch.setenv("PRACTICE_RATE_LIMIT_PER_MINUTE", "3")
        get_settings.cache_clear()
        practice_service.reset_rate_limit()

        try:
            for _ in range(3):
                practice_service.start_session(
                    db, candidate_user, PracticeSessionCreate(size=1)
                )
            with pytest.raises(BusinessError) as exc:
                practice_service.start_session(
                    db, candidate_user, PracticeSessionCreate(size=1)
                )
            assert "过于频繁" in exc.value.message
        finally:
            get_settings.cache_clear()
            practice_service.reset_rate_limit()

    def test_is_per_user(self, db, candidate_user, other_candidate, practice_questions, monkeypatch):
        monkeypatch.setenv("PRACTICE_RATE_LIMIT_PER_MINUTE", "1")
        get_settings.cache_clear()
        practice_service.reset_rate_limit()

        try:
            practice_service.start_session(
                db, candidate_user, PracticeSessionCreate(size=1)
            )
            with pytest.raises(BusinessError):
                practice_service.start_session(
                    db, candidate_user, PracticeSessionCreate(size=1)
                )
            # 另一位候选人不受影响
            practice_service.start_session(
                db, other_candidate, PracticeSessionCreate(size=1)
            )
        finally:
            get_settings.cache_clear()
            practice_service.reset_rate_limit()

    def test_window_slides(self, db, candidate_user, practice_questions, monkeypatch):
        """窗口外的旧时间戳被剔除后，请求重新放行。"""
        monkeypatch.setenv("PRACTICE_RATE_LIMIT_PER_MINUTE", "1")
        monkeypatch.setattr(practice_service, "RATE_WINDOW_SECONDS", 0)
        get_settings.cache_clear()
        practice_service.reset_rate_limit()

        try:
            practice_service.start_session(
                db, candidate_user, PracticeSessionCreate(size=1)
            )
            # 窗口长度 0 → 上一次的时间戳立即过期，因此这次仍可放行
            practice_service.start_session(
                db, candidate_user, PracticeSessionCreate(size=1)
            )
        finally:
            get_settings.cache_clear()
            practice_service.reset_rate_limit()


# ============== 预览 ==============


class TestPreview:
    def test_preview_has_no_answer_fields(self, db, candidate_user, practice_questions):
        items = practice_service.preview_questions(db, candidate_user, PracticeFilters(), None)
        assert len(items) == 4
        for item in items:
            assert "reference_answer" not in item
            assert "explanation" not in item
            assert "source" not in item
            assert "created_by" not in item

    def test_preview_keeps_options(self, db, candidate_user, practice_questions):
        items = practice_service.preview_questions(db, candidate_user, PracticeFilters(), None)
        single = next(i for i in items if i["question_type"] == "single_choice")
        assert single["options"]


# ============ MVP-3：按简历推荐取题（module-20 §7.1 – §7.4）============


class _MatchStub(MockProvider):
    """只覆写「按简历匹配」那一路，并记录调用参数。

    继承 `MockProvider` 而非直接实现 `AIProvider`：后者是 ABC，每新增一个抽象
    方法都会让本类无法实例化。
    """

    def __init__(self, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def match_questions_by_resume(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return list(self._result or [])


def _matched(question_ids, reason="与简历相关"):
    return [MatchedQuestion(question_id=qid, reason=reason) for qid in question_ids]


def _seed_extra(db, position, owner, count, dimension="沟通能力"):
    """再落 count 道题，把候选池撑到足以体现「池子被放大」。"""
    created = [
        question_repository.create(
            db,
            position_id=position.id,
            category="通用",
            dimension=dimension,
            content=f"推荐池第{i}题的内容描述文本",
            difficulty="medium",
            tags=[],
            source="bank",
            question_type="short_answer",
            reference_answer=f"推荐池第{i}题的参考答案",
            explanation=f"推荐池第{i}题的解析",
            created_by=owner.id,
        )
        for i in range(count)
    ]
    db.commit()
    for question in created:
        db.refresh(question)
    return created


def _question_ids(detail) -> list[int]:
    return [item.question["id"] for item in detail.items]


def _start(db, user, **kwargs):
    return practice_service.start_session(db, user, PracticeSessionCreate(**kwargs))


def _session_count(db) -> int:
    from sqlalchemy import func, select

    return db.execute(select(func.count(PracticeSession.id))).scalar_one()


# ------------------------- §7.1 未关联简历：零回归 -------------------------


class TestNoResumeUnchanged:
    def test_without_resume_has_null_fields(self, db, candidate_user, practice_questions):
        detail = _start(db, candidate_user, size=2)

        assert detail.resume_id is None
        assert detail.resume_match_applied is False

    def test_without_resume_returns_filter_results(
        self, db, candidate_user, practice_questions
    ):
        detail = _start(db, candidate_user, size=2)
        expected = question_repository.list_practice_candidates(db, PracticeFilters(), 2)

        assert _question_ids(detail) == [question.id for question in expected]

    def test_without_resume_does_not_call_ai(
        self, db, candidate_user, practice_questions, monkeypatch
    ):
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        detail = _start(db, candidate_user, size=2)

        assert stub.calls == []  # 连调用都没有
        assert detail.resume_match_applied is False


# ------------------------- §7.2 正常路径 -------------------------


class TestResumeMatchApplied:
    def test_applies_match(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        wanted = [question.id for question in practice_questions[:3]]
        _use_provider(monkeypatch, _MatchStub(result=_matched(wanted)))

        detail = _start(db, candidate_user, size=3, resume_id=resume.id)

        assert detail.resume_match_applied is True
        assert detail.resume_id == resume.id
        assert _question_ids(detail) == wanted

    def test_orders_by_match_result(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """会话内顺序 **就是** AI 的相关度顺序 —— 本模块不二次排序。"""
        reversed_ids = [question.id for question in reversed(practice_questions)]
        _use_provider(monkeypatch, _MatchStub(result=_matched(reversed_ids)))

        detail = _start(
            db, candidate_user, size=4, resume_id=resume.id, position_id=None
        )

        assert _question_ids(detail) == reversed_ids

    def test_uses_larger_pool(
        self, db, candidate_user, position, hr_user, practice_questions, resume, monkeypatch
    ):
        """池子必须比 size 大，否则 AI 只能重排、不能改选。"""
        _seed_extra(db, position, hr_user, 12)  # 池 = 4 + 12 = 16
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=3, resume_id=resume.id)

        assert len(stub.calls[0]["candidates"]) == 12  # min(3*4, 100)
        assert 12 > 3

    def test_pool_size_formula(self):
        assert practice_service._resume_pool_size(3) == 12
        assert practice_service._resume_pool_size(20) == 80
        assert practice_service._resume_pool_size(50) == 100  # 上限护栏

    def test_pool_capped_at_max(
        self, db, candidate_user, position, hr_user, practice_questions, resume, monkeypatch
    ):
        _seed_extra(db, position, hr_user, 30)
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=20, resume_id=resume.id)

        assert len(stub.calls[0]["candidates"]) <= practice_service._RESUME_POOL_MAX

    def test_passes_resume_content(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=2, resume_id=resume.id)

        assert stub.calls[0]["resume_text"] == resume.content

    def test_derives_dims_from_pool(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """dims 由**池内维度**推导：既绕开 position 依赖，又保证必然非空。"""
        expected = sorted({question.dimension for question in practice_questions})
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=2, resume_id=resume.id)

        assert stub.calls[0]["dims"] == expected

    def test_position_name_from_supply(
        self, db, candidate_user, position, practice_questions, resume, monkeypatch
    ):
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=2, resume_id=resume.id, position_id=position.id)
        assert stub.calls[0]["position_name"] == position.name

        _start(db, candidate_user, size=2, resume_id=resume.id)
        assert stub.calls[1]["position_name"] == ""  # 未指定岗位

    def test_jd_is_empty(
        self, db, candidate_user, position, practice_questions, resume, monkeypatch
    ):
        """刷题没有 JD 上下文；该供给刻意不下发 JD（PRD §4.7）。"""
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        _start(db, candidate_user, size=2, resume_id=resume.id, position_id=position.id)

        assert stub.calls[0]["jd"] == ""

    def test_writes_snapshots(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """推荐不改变快照机制 —— 5 个快照字段照写。"""
        wanted = [question.id for question in practice_questions[:2]]
        _use_provider(monkeypatch, _MatchStub(result=_matched(wanted)))

        detail = _start(db, candidate_user, size=2, resume_id=resume.id)

        by_id = {question.id: question for question in practice_questions}
        for item in detail.items:
            question = by_id[item.question["id"]]
            assert item.question["content"] == question.content
            assert item.question["dimension"] == question.dimension
            assert item.question["question_type"] == question.question_type

    def test_seq_starts_at_one(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        wanted = [question.id for question in practice_questions[:3]]
        _use_provider(monkeypatch, _MatchStub(result=_matched(wanted)))

        detail = _start(db, candidate_user, size=3, resume_id=resume.id)

        assert [item.seq for item in detail.items] == [1, 2, 3]


# ------------------------- §7.3 降级路径（最重要的测试组）-------------------------


class TestResumeMatchDegradation:
    def test_ai_failure_degrades(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        _use_provider(monkeypatch, _MatchStub(error=AIProviderError("模拟推荐失败")))

        detail = _start(db, candidate_user, size=2, resume_id=resume.id)

        assert len(detail.items) == 2  # 照常建成
        assert detail.resume_match_applied is False

    def test_ai_failure_keeps_resume_id(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """降级时 resume_id 仍保留 —— 它表达「候选人想用哪份」这一事实。"""
        _use_provider(monkeypatch, _MatchStub(error=AIProviderError("模拟推荐失败")))

        detail = _start(db, candidate_user, size=2, resume_id=resume.id)

        assert detail.resume_id == resume.id

    def test_ai_failure_result_equals_no_resume(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """降级取到的题与「不传 resume_id」**逐条相同**（同一入口取前缀）。"""
        _use_provider(monkeypatch, _MatchStub(error=AIProviderError("模拟推荐失败")))
        degraded = _start(db, candidate_user, size=2, resume_id=resume.id)

        plain = _start(db, candidate_user, size=2)

        assert _question_ids(degraded) == _question_ids(plain)

    def test_ai_failure_still_counts_rate_limit(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        monkeypatch.setenv("PRACTICE_RATE_LIMIT_PER_MINUTE", "1")
        get_settings.cache_clear()
        practice_service.reset_rate_limit()

        try:
            _use_provider(
                monkeypatch, _MatchStub(error=AIProviderError("模拟推荐失败"))
            )
            _start(db, candidate_user, size=1, resume_id=resume.id)

            with pytest.raises(BusinessError):
                _start(db, candidate_user, size=1)
        finally:
            get_settings.cache_clear()
            practice_service.reset_rate_limit()

    def test_ai_empty_result_degrades(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        _use_provider(monkeypatch, _MatchStub(result=[]))

        detail = _start(db, candidate_user, size=2, resume_id=resume.id)

        expected = question_repository.list_practice_candidates(db, PracticeFilters(), 2)
        assert detail.resume_match_applied is False
        assert _question_ids(detail) == [question.id for question in expected]

    def test_ai_unknown_ids_degrade_safely(
        self, db, candidate_user, practice_questions, resume, monkeypatch
    ):
        """池外 id 全部被过滤 → picked 为空 → 安全降级（不建空会话）。"""
        _use_provider(monkeypatch, _MatchStub(result=_matched([999999, 888888])))

        detail = _start(db, candidate_user, size=2, resume_id=resume.id)

        assert detail.resume_match_applied is False
        assert len(detail.items) == 2

    def test_log_levels_distinguish_failure_from_miss(
        self, db, candidate_user, practice_questions, resume, monkeypatch, caplog
    ):
        """故障走 warning、正常未命中走 info —— 两者都降级，但可区分。"""
        with caplog.at_level("INFO"):
            _use_provider(monkeypatch, _MatchStub(result=[]))
            _start(db, candidate_user, size=2, resume_id=resume.id)
            miss_records = [
                r for r in caplog.records if "按简历推荐未命中" in r.getMessage()
            ]
            assert miss_records and all(r.levelname == "INFO" for r in miss_records)

            caplog.clear()
            _use_provider(
                monkeypatch, _MatchStub(error=AIProviderError("模拟推荐失败"))
            )
            _start(db, candidate_user, size=2, resume_id=resume.id)
            fail_records = [
                r for r in caplog.records if "按简历推荐失败" in r.getMessage()
            ]
            assert fail_records and all(r.levelname == "WARNING" for r in fail_records)

    def test_pool_empty_reports_409_and_creates_nothing(
        self, db, candidate_user, resume
    ):
        with pytest.raises(BusinessError) as exc:
            _start(
                db,
                candidate_user,
                size=2,
                resume_id=resume.id,
                dimension="不存在的维度",
            )

        assert "没有符合条件的题目" in exc.value.message
        assert _session_count(db) == 0  # 不建空会话


# ------------------------- §7.4 归属与隔离 -------------------------


class TestResumeOwnership:
    def test_other_candidates_resume_403(
        self, db, candidate_user, other_resume, practice_questions
    ):
        with pytest.raises(ForbiddenError):
            _start(db, candidate_user, size=2, resume_id=other_resume.id)

    def test_missing_resume_404(self, db, candidate_user, practice_questions):
        with pytest.raises(NotFoundError):
            _start(db, candidate_user, size=2, resume_id=999999)

    def test_validation_precedes_picking(
        self, db, candidate_user, other_resume, practice_questions, monkeypatch
    ):
        """归属校验先于取题：越权时不该查题、更不该调 AI、也不该建会话。"""
        stub = _MatchStub(result=_matched([practice_questions[0].id]))
        _use_provider(monkeypatch, stub)

        with pytest.raises(ForbiddenError):
            _start(db, candidate_user, size=2, resume_id=other_resume.id)

        assert stub.calls == []
        assert _session_count(db) == 0
