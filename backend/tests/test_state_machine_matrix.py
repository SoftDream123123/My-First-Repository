"""interview 状态机全矩阵测试。

计划书 §5.4.1 定义了 5 个状态与 8 条合法迁移，其余 17 组一律拒绝并携带
detail={from,to}。逐条写用例容易漏掉某个非法组合，这里用数据驱动把 5×5
全矩阵一次性钉死 —— 少一条合法迁移、多一条非法迁移都会立刻失败。

两层验证：
  1. test_transition_matrix —— 直接打状态机的唯一权威 _assert_transition，
     覆盖全部 25 组（含没有入口的 draft）。
  2. test_entry_point_*     —— 走真实入口函数，覆盖四个可达目标，
     确认入口确实接在状态机上而不是绕过了它。
"""

import pytest

from app.core.exceptions import BusinessError
from app.interview import repository
from app.interview import service as interview_service
from app.interview.models import (
    STATUS_COMPLETED,
    STATUS_DRAFT,
    STATUS_EVALUATED,
    STATUS_EVALUATING,
    STATUS_ONGOING,
)
from app.interview.schemas import InterviewCreate

ALL_STATES = [
    STATUS_DRAFT,
    STATUS_ONGOING,
    STATUS_COMPLETED,
    STATUS_EVALUATING,
    STATUS_EVALUATED,
]

# draft 没有迁移入口（它是事务内的瞬时值，从不落库），故不在入口层测试范围内
REACHABLE_TARGETS = [STATUS_ONGOING, STATUS_COMPLETED, STATUS_EVALUATING, STATUS_EVALUATED]

# 计划书 §5.4.1 的 8 条合法迁移
ALLOWED_TRANSITIONS = {
    (STATUS_DRAFT, STATUS_ONGOING),
    (STATUS_ONGOING, STATUS_COMPLETED),
    (STATUS_COMPLETED, STATUS_EVALUATING),
    (STATUS_COMPLETED, STATUS_ONGOING),
    (STATUS_EVALUATING, STATUS_EVALUATED),
    (STATUS_EVALUATING, STATUS_COMPLETED),
    (STATUS_EVALUATED, STATUS_EVALUATING),
    (STATUS_EVALUATED, STATUS_ONGOING),
}


def _perform(db, user, interview_id: int, target: str) -> None:
    """按目标状态调用对应迁移入口 —— 与各端点使用的入口一一对应。"""
    if target == STATUS_ONGOING:
        interview_service.rollback_interview(db, user, interview_id)
    elif target == STATUS_COMPLETED:
        interview_service.complete_interview(db, user, interview_id)
    elif target == STATUS_EVALUATING:
        interview_service.transition_to_evaluating(db, interview_id)
    elif target == STATUS_EVALUATED:
        interview_service.transition_to_evaluated(db, interview_id)
    else:
        raise AssertionError(f"没有迁移入口可以到达 {target}")


@pytest.fixture
def interview_in(db, hr_user, position):
    """把面试摆到指定状态 —— 仅测试装帧，不经过状态机。"""

    def _make(status: str) -> int:
        detail = interview_service.create_interview(
            db, hr_user, InterviewCreate(position_id=position.id, candidate_name="张三")
        )
        interview = repository.get_by_id(db, detail.id)
        interview.status = status
        interview.completed_at = None
        db.commit()
        return interview.id

    return _make


def test_matrix_has_expected_shape():
    """8 条合法 / 17 条非法 —— 防止 ALLOWED 集合被误改。"""
    assert len(ALLOWED_TRANSITIONS) == 8
    assert len(ALL_STATES) ** 2 - len(ALLOWED_TRANSITIONS) == 17


@pytest.mark.parametrize("target", ALL_STATES)
@pytest.mark.parametrize("source", ALL_STATES)
def test_transition_matrix(source, target):
    """状态机权威层：25 组 (from, to) 逐格验证。"""
    if (source, target) in ALLOWED_TRANSITIONS:
        interview_service._assert_transition(source, target)  # 不应抛错
    else:
        with pytest.raises(BusinessError) as excinfo:
            interview_service._assert_transition(source, target)
        assert excinfo.value.detail == {"from": source, "to": target}


@pytest.mark.parametrize("target", REACHABLE_TARGETS)
@pytest.mark.parametrize("source", ALL_STATES)
def test_entry_point_respects_matrix(db, hr_user, interview_in, source, target):
    """入口层：真实入口函数必须与状态机矩阵一致，且失败时不改状态。"""
    interview_id = interview_in(source)

    if (source, target) in ALLOWED_TRANSITIONS:
        _perform(db, hr_user, interview_id, target)
        db.expire_all()
        assert repository.get_by_id(db, interview_id).status == target
    else:
        with pytest.raises(BusinessError):
            _perform(db, hr_user, interview_id, target)

        db.expire_all()
        assert repository.get_by_id(db, interview_id).status == source


def test_completed_at_set_on_complete_and_cleared_on_rollback(db, hr_user, interview_in):
    """§5.4.1 副作用：completed → ongoing 必须清空 completed_at。"""
    interview_id = interview_in(STATUS_ONGOING)

    interview_service.complete_interview(db, hr_user, interview_id)
    assert repository.get_by_id(db, interview_id).completed_at is not None

    interview_service.rollback_interview(db, hr_user, interview_id)
    assert repository.get_by_id(db, interview_id).completed_at is None


def test_begin_evaluation_is_idempotent(db, hr_user, interview_in):
    """begin_evaluation 在 evaluating 下必须是无副作用的幂等操作。"""
    interview_id = interview_in(STATUS_COMPLETED)

    interview_service.begin_evaluation(db, interview_id)
    assert repository.get_by_id(db, interview_id).status == STATUS_EVALUATING

    interview_service.begin_evaluation(db, interview_id)  # 不应抛错
    assert repository.get_by_id(db, interview_id).status == STATUS_EVALUATING
