"""question 模块 HTTP 端点。"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth.models import ROLE_ADMIN, ROLE_HR, User
from app.core.deps import get_db, require_roles
from app.question import service
from app.question.schemas import (
    QuestionCreate,
    QuestionFilters,
    QuestionOut,
    QuestionUpdate,
)

router = APIRouter(prefix="/questions", tags=["题库"])

# 本模块全部端点均为 HR 侧：admin 与 hr 均可，candidate 一律 403（PRD §4.1）。
_hr_guard = require_roles(ROLE_ADMIN, ROLE_HR)


@router.post(
    "",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建题目",
)
def create_question(
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> QuestionOut:
    return QuestionOut.model_validate(service.create_question(db, user, payload))


@router.get("", response_model=list[QuestionOut], summary="题目列表（多维筛选）")
def list_questions(
    position_id: int | None = Query(default=None, description="按岗位过滤"),
    category: str | None = Query(default=None, description="精确匹配分类"),
    dimension: str | None = Query(default=None, description="精确匹配维度"),
    source: str | None = Query(default=None, description="bank | ai"),
    question_type: str | None = Query(
        default=None, description="single_choice | short_answer"
    ),
    keyword: str | None = Query(default=None, description="按题干模糊匹配"),
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> list[QuestionOut]:
    filters = QuestionFilters(
        position_id=position_id,
        category=category,
        dimension=dimension,
        source=source,
        question_type=question_type,
        keyword=keyword,
    )
    return [
        QuestionOut.model_validate(q)
        for q in service.list_questions(db, user, filters)
    ]


@router.get("/{question_id}", response_model=QuestionOut, summary="题目详情")
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> QuestionOut:
    return QuestionOut.model_validate(service.get_question(db, user, question_id))


@router.put("/{question_id}", response_model=QuestionOut, summary="更新题目")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> QuestionOut:
    return QuestionOut.model_validate(
        service.update_question(db, user, question_id, payload)
    )


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除题目",
)
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> Response:
    service.delete_question(db, user, question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{question_id}/reference-answer",
    response_model=QuestionOut,
    summary="调 AI 生成参考答案与解析并落库",
)
def generate_reference_answer(
    question_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_hr_guard),
) -> QuestionOut:
    """无请求体 —— 题目信息从路径与库中读取，避免客户端指定生成依据。

    单选题若 AI 给出的答案不在选项内，返回 409 且**不落库**（见 service）。
    """
    return QuestionOut.model_validate(
        service.generate_reference_answer(db, user, question_id)
    )
