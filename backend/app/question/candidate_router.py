"""question 模块的候选人侧端点。

与 HR 端点分文件：两组端点的守卫不同（candidate vs admin/hr），放在同一
router 里容易在新增端点时挂错守卫 —— 而「挂错守卫」正是权限守卫补全要修的
那类问题。按守卫分文件，让「这个文件里的端点都是同一类角色」成为可读的事实。

为什么这条路由落在 question 包而不是 position 包：它的数据是「**有题目的岗位**」
—— 查询以 question 表按 position_id 分组为驱动，再联 position 取名称。若放
position 包，position 就必须读 question 表，而架构约束禁止该方向
（FORBIDDEN_DEPENDENCIES 中 position 禁止依赖 question）。question → position
是允许的，因此这条查询只能由 question 包提供。position 模块本次零改动。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.deps import get_db, require_roles
from app.question import service
from app.question.schemas import PracticePositionOut

router = APIRouter(prefix="/candidate", tags=["刷题（候选人）"])

# 候选人侧守卫精确匹配 —— admin 与 hr 在此不通行（见 module-09 §4.5）
_candidate_guard = require_roles("candidate")


@router.get(
    "/positions",
    response_model=list[PracticePositionOut],
    summary="刷题岗位筛选项（有题目的岗位）",
)
def list_practice_positions(
    db: Session = Depends(get_db),
    _: User = Depends(_candidate_guard),
) -> list[PracticePositionOut]:
    """只下发岗位 id / 名称 / 题量，**不含 JD**。

    不给这个接口的话，前端只能从「已参与面试的岗位」拼凑筛选项，会漏掉候选人
    没有面过的岗位 —— 而他恰恰最需要练这些。口径与取题一致（不按 created_by
    过滤），才能让「筛选项」与「取得到的题」自洽。
    """
    return service.list_practice_positions(db)
