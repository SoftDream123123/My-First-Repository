"""resume 模块业务逻辑：归属校验、长度校验，以及两个跨包供给口子。

**本模块不 import interview / practice** —— 删除保护完全交给外键 RESTRICT，
因此不产生任何反向依赖（PRD §9）。
"""

from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.models import User
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.resume import repository
from app.resume.models import Resume
from app.resume.schemas import ResumeCreate, ResumeUpdate


class ContentTooLongError(ValidationError):
    """简历正文超长 —— **全项目唯一一处 422**（PRD §7 明确要求）。

    错误码仍是既有的 `VALIDATION_ERROR`（不新增错误码），只有 HTTP 状态码
    不同。刻意不做成通用的 400：超长是「内容超出承载力」，与「参数格式不对」
    不是同一类问题，且前端据此区分提示文案。
    """

    status_code = 422


def _field_error(field: str, message: str) -> ValidationError:
    """构造与全局校验处理器**同形**的 400 响应体（`detail.fields`）。"""
    return ValidationError(
        "请求参数不合法",
        detail={"fields": [{"field": field, "message": message, "type": "value_error"}]},
    )


def _clean_required(value: str, field: str) -> str:
    """去首尾空白并校验非空。

    一份只有空格的简历会让 AI 匹配与准备助手拿到空洞输入并产出无意义结果，
    属于「可预防的坏数据」。
    """
    cleaned = value.strip()
    if not cleaned:
        raise _field_error(field, "不能为空")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    return None if value is None else value.strip()


def _validate_content_length(content: str) -> None:
    limit = get_settings().resume_content_max_length
    if len(content) > limit:
        raise ContentTooLongError(f"简历正文不能超过 {limit} 字符")


def create_resume(db: Session, user: User, data: ResumeCreate) -> Resume:
    title = _clean_required(data.title, "title")
    content = _clean_required(data.content, "content")
    _validate_content_length(content)

    resume = repository.create(
        db,
        title=title,
        content=content,
        candidate_name=_clean_optional(data.candidate_name),
        candidate_contact=_clean_optional(data.candidate_contact),
        created_by=user.id,  # 归属恒取自 token，请求体里没有这个字段
    )
    db.commit()
    db.refresh(resume)
    return resume


def list_my_resumes(db: Session, user: User, limit: int) -> list[Resume]:
    """只查本人。守卫是 candidate，admin 不通行，因此不需要 admin 放开逻辑。"""
    return repository.list_by_creator(db, user.id, limit)


def get_my_resume(db: Session, user: User, resume_id: int) -> Resume:
    """取回本人简历。

    用 `ensure_owner_match` 而非 `ensure_resource_visible`：后者对 candidate
    角色会直接抛 403（module-16 的纵深防御），候选人连自己的简历都读不到。

    先查存在性（404）再判归属（403），与全项目一致。
    """
    resume = repository.get_by_id(db, resume_id)
    if resume is None:
        raise NotFoundError("简历不存在")
    auth_service.ensure_owner_match(user, resume.created_by, "简历")
    return resume


def update_resume(
    db: Session, user: User, resume_id: int, data: ResumeUpdate
) -> Resume:
    """部分更新：只处理请求里**给了值**的字段，其余保持不变。"""
    resume = get_my_resume(db, user, resume_id)

    fields: dict[str, object] = {}
    if data.title is not None:
        fields["title"] = _clean_required(data.title, "title")

    if data.content is not None:
        content = _clean_required(data.content, "content")
        _validate_content_length(content)
        fields["content"] = content

    if data.candidate_name is not None:
        fields["candidate_name"] = data.candidate_name.strip()

    if data.candidate_contact is not None:
        fields["candidate_contact"] = data.candidate_contact.strip()

    if fields:
        repository.update(db, resume, **fields)
        db.commit()
        db.refresh(resume)

    return resume


def delete_resume(db: Session, user: User, resume_id: int) -> None:
    resume = get_my_resume(db, user, resume_id)
    repository.delete(db, resume)


# ---------------------------- 跨包供给契约 ----------------------------
# 这两个函数是 resume 对外最重要的两个口子，**权限语义完全相反**，故必须分开。


def load_unchecked(db: Session, resume_id: int) -> Resume | None:
    """纯读，**不做任何权限判断**；不存在返回 None。

    名字里的 `unchecked` 是刻意的：让「这里没有权限检查」在调用点一眼可见，
    避免有人把它误当成安全入口。HR 读的是**别人的**（候选人的）简历，
    任何归属校验都必然失败 —— HR 的读取判据（该简历关联到自己名下的某场面试）
    需要读 interview 表，因此只能由 interview 实现（PRD §9）。
    """
    return repository.get_by_id(db, resume_id)


def ensure_mine(db: Session, user: User, resume_id: int) -> Resume:
    """校验「这份简历是我的」并返回；不存在 404 / 非本人 403。

    供 interview（候选人把简历关联到面试）与 practice（按简历推荐）调用。
    """
    return get_my_resume(db, user, resume_id)
