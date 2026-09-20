"""resume 模块 service / repository 层测试（计划书 module-17 §7.1 / §7.3 / §7.4 / §7.7）。

⚠️ 计划书 §7.4 里另外三条用例 —— 「被面试关联 → 409」「被练习关联 → 409」
「冲突后 rollback 且 session 可用」—— 依赖 `interview.resume_id`（module-19）
与 `practice_session.resume_id`（module-20）两个外键列。本模块提交时这两列
**尚不存在**，因此在这两个模块落地时补写（开工前已与用户确认的推迟方案）。
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update as sa_update

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.resume import repository, service
from app.resume.models import Resume
from app.resume.schemas import ResumeCreate, ResumeUpdate


def _now() -> datetime:
    """naive UTC —— 与数据库列（无时区 DATETIME）同一基准。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _create(db, user, title="张三-后端开发", content="五年 Python 后端经验。", **extra):
    return service.create_resume(
        db, user, ResumeCreate(title=title, content=content, **extra)
    )


def _backdate(db, resume: Resume, when: datetime) -> None:
    """把 created_at / updated_at 压到指定时刻。

    时间戳是**秒精度**（MySQL DATETIME），同一秒内的两次写入无法区分先后。
    需要断言「先后顺序」的用例一律先制造一个可区分的历史时刻，再走真实路径 ——
    而不是 sleep 一秒（那是时间竞态，机器一卡就红）。
    """
    db.execute(
        sa_update(Resume)
        .where(Resume.id == resume.id)
        .values(created_at=when, updated_at=when)
    )
    db.commit()


# ==================== 创建与校验（§7.1）====================


class TestCreate:
    def test_persists_all_fields(self, db, candidate_user):
        created = _create(
            db,
            candidate_user,
            title="张三-后端开发",
            content="五年 Python 后端经验。",
            candidate_name="张三",
            candidate_contact="zhangsan@example.com",
        )

        assert created.id is not None
        assert created.title == "张三-后端开发"
        assert created.content == "五年 Python 后端经验。"
        assert created.candidate_name == "张三"
        assert created.candidate_contact == "zhangsan@example.com"

    def test_created_by_comes_from_user_not_payload(self, db, candidate_user):
        """归属恒取自 token —— 请求体里根本没有这个字段。"""
        assert "created_by" not in ResumeCreate.model_fields

        created = _create(db, candidate_user)
        assert created.created_by == candidate_user.id

    def test_rejects_blank_title(self, db, candidate_user):
        with pytest.raises(ValidationError) as exc:
            _create(db, candidate_user, title="   ")
        assert exc.value.status_code == 400

    def test_rejects_blank_content(self, db, candidate_user):
        with pytest.raises(ValidationError) as exc:
            _create(db, candidate_user, content="\n  \t ")
        assert exc.value.status_code == 400

    def test_trims_whitespace(self, db, candidate_user):
        created = _create(db, candidate_user, title="  张三-后端  ", content="  正文  ")
        assert created.title == "张三-后端"
        assert created.content == "正文"

    def test_content_at_limit_ok(self, db, candidate_user):
        limit = get_settings().resume_content_max_length
        created = _create(db, candidate_user, content="正" * limit)
        assert len(created.content) == limit

    def test_content_over_limit_is_422_not_400(self, db, candidate_user):
        """PRD §7 要求 422。全项目唯一一处不按 400 收口的参数校验。

        若有人把长度校验挪进 Pydantic 的 `max_length`，它会落进 main.py 的
        RequestValidationError 处理器变成 400 —— 这条用例就是拦住那次「统一」的。
        """
        limit = get_settings().resume_content_max_length
        with pytest.raises(ValidationError) as exc:
            _create(db, candidate_user, content="正" * (limit + 1))

        assert exc.value.status_code == 422
        assert exc.value.code == "VALIDATION_ERROR"  # 不新增错误码

    def test_allows_duplicate_title(self, db, candidate_user):
        """刻意不加 (created_by, title) 唯一约束：同名简历是无害的正当用法。"""
        first = _create(db, candidate_user, title="通用简历")
        second = _create(db, candidate_user, title="通用简历")
        assert first.id != second.id

    def test_optional_fields_nullable(self, db, candidate_user):
        created = _create(db, candidate_user)
        assert created.candidate_name is None
        assert created.candidate_contact is None


# ==================== 列表（§7.2 的 service 侧）====================


class TestList:
    def test_only_own(self, db, candidate_user, other_candidate):
        mine = _create(db, candidate_user, title="我的简历")
        _create(db, other_candidate, title="别人的简历")

        assert [r.id for r in service.list_my_resumes(db, candidate_user, 50)] == [mine.id]

    def test_ordered_by_updated_desc(self, db, candidate_user):
        older = _create(db, candidate_user, title="早改的")
        newer = _create(db, candidate_user, title="晚改的")

        base = _now()
        _backdate(db, older, base - timedelta(hours=2))
        _backdate(db, newer, base - timedelta(hours=1))

        listed = service.list_my_resumes(db, candidate_user, 50)
        assert [r.id for r in listed] == [newer.id, older.id]

    def test_empty_returns_empty_list(self, db, candidate_user):
        assert service.list_my_resumes(db, candidate_user, 50) == []


# ==================== 详情 / 更新 / 删除（§7.3 / §7.4）====================


class TestGetUpdateDelete:
    def test_get_own_ok(self, db, candidate_user):
        created = _create(db, candidate_user)
        assert service.get_my_resume(db, candidate_user, created.id).id == created.id

    def test_get_missing_404(self, db, candidate_user):
        with pytest.raises(NotFoundError):
            service.get_my_resume(db, candidate_user, 999999)

    def test_get_other_candidates_403(self, db, candidate_user, other_candidate):
        theirs = _create(db, other_candidate)
        with pytest.raises(ForbiddenError):
            service.get_my_resume(db, candidate_user, theirs.id)

    def test_update_partial_title_only(self, db, candidate_user):
        created = _create(db, candidate_user, title="旧标题", content="原正文")
        updated = service.update_resume(
            db, candidate_user, created.id, ResumeUpdate(title="新标题")
        )

        assert updated.title == "新标题"
        assert updated.content == "原正文"  # 未提供的字段保持不变

    def test_update_partial_content_only(self, db, candidate_user):
        created = _create(db, candidate_user, title="原标题", content="原正文")
        updated = service.update_resume(
            db, candidate_user, created.id, ResumeUpdate(content="新正文")
        )

        assert updated.title == "原标题"
        assert updated.content == "新正文"

    def test_update_bumps_updated_at(self, db, candidate_user):
        created = _create(db, candidate_user)
        _backdate(db, created, _now() - timedelta(hours=1))

        updated = service.update_resume(
            db, candidate_user, created.id, ResumeUpdate(title="改过的标题")
        )
        assert updated.updated_at > updated.created_at

    def test_update_other_candidates_403(self, db, candidate_user, other_candidate):
        theirs = _create(db, other_candidate)
        with pytest.raises(ForbiddenError):
            service.update_resume(
                db, candidate_user, theirs.id, ResumeUpdate(title="想改别人的")
            )

    def test_update_content_over_limit_422(self, db, candidate_user):
        created = _create(db, candidate_user)
        limit = get_settings().resume_content_max_length

        with pytest.raises(ValidationError) as exc:
            service.update_resume(
                db, candidate_user, created.id, ResumeUpdate(content="正" * (limit + 1))
            )
        assert exc.value.status_code == 422

    def test_update_cannot_rewrite_owner(self, db, candidate_user):
        """请求体里没有 created_by，因此归属无从改写。"""
        assert "created_by" not in ResumeUpdate.model_fields

        created = _create(db, candidate_user)
        updated = service.update_resume(
            db, candidate_user, created.id, ResumeUpdate(title="新标题")
        )
        assert updated.created_by == candidate_user.id

    def test_update_empty_payload_is_noop(self, db, candidate_user):
        created = _create(db, candidate_user, title="原标题")
        same = service.update_resume(db, candidate_user, created.id, ResumeUpdate())
        assert same.title == "原标题"

    def test_delete_unreferenced_ok(self, db, candidate_user):
        created = _create(db, candidate_user)
        service.delete_resume(db, candidate_user, created.id)

        assert repository.get_by_id(db, created.id) is None

    def test_delete_other_candidates_403(self, db, candidate_user, other_candidate):
        theirs = _create(db, other_candidate)
        with pytest.raises(ForbiddenError):
            service.delete_resume(db, candidate_user, theirs.id)

    def test_delete_missing_404(self, db, candidate_user):
        with pytest.raises(NotFoundError):
            service.delete_resume(db, candidate_user, 999999)


# ==================== 跨包供给契约（§7.7）====================


class TestCrossPackageContract:
    def test_load_unchecked_returns_other_users_resume(
        self, db, candidate_user, other_candidate
    ):
        """证明它**确实不做权限过滤** —— HR 读的正是别人的简历。

        若有人「顺手」在这里补一层归属校验，HR 侧读简历会全线 403，
        这条用例会立刻变红。
        """
        theirs = _create(db, other_candidate, title="李四-前端开发")
        loaded = service.load_unchecked(db, theirs.id)
        assert loaded is not None
        assert loaded.id == theirs.id

    def test_load_unchecked_missing_returns_none(self, db):
        """不存在返回 None 而非抛错 —— 404 语义由调用方决定。"""
        assert service.load_unchecked(db, 999999) is None

    def test_ensure_mine_ok(self, db, candidate_user):
        created = _create(db, candidate_user)
        assert service.ensure_mine(db, candidate_user, created.id).id == created.id

    def test_ensure_mine_other_user_403(self, db, candidate_user, other_candidate):
        theirs = _create(db, other_candidate)
        with pytest.raises(ForbiddenError):
            service.ensure_mine(db, candidate_user, theirs.id)

    def test_ensure_mine_missing_404(self, db, candidate_user):
        with pytest.raises(NotFoundError):
            service.ensure_mine(db, candidate_user, 999999)
