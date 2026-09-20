"""测试夹具。

关键约定：
1. 环境变量必须在导入任何 app 模块**之前**设置 —— app.core.db 在导入时
   即根据 DATABASE_URL 创建 engine。
2. 测试使用独立的 MySQL 测试库，与开发库物理隔离。
3. 每个测试前清空全部业务表，保证用例之间互不干扰。
"""

import os

# ------------------------------------------------------------------
# 环境变量必须先于 app 导入设置
# ------------------------------------------------------------------
os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://root:123456@127.0.0.1:3306/interview_test?charset=utf8mb4",
)
os.environ.setdefault("JWT_SECRET", "pytest-only-secret-do-not-use-in-production")
os.environ.setdefault("PROVIDER_NAME", "mock")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # 测试提速（生产默认 12）

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token  # noqa: E402

# 导入全部模型，确保 Base.metadata 完整（否则 create_all 会漏表）
# 新增业务模块时，必须在此处补上对应的 models 导入。
import app.auth.models  # noqa: E402,F401
import app.evaluation.models  # noqa: E402,F401
import app.interview.models  # noqa: E402,F401
import app.position.models  # noqa: E402,F401
import app.question.models  # noqa: E402,F401


def _ensure_database(url: str) -> None:
    """确保测试库存在（不存在则创建）。

    注意：不能用 URL.set(database=None) —— SQLAlchemy 2.0 的 set() 把 None
    视为「保持原值」，数据库名不会被清除。必须显式重建不含 database 的 URL。
    """
    parsed = make_url(url)
    db_name = parsed.database
    if not db_name:
        raise RuntimeError("DATABASE_URL 未指定数据库名")

    server_url = URL.create(
        drivername=parsed.drivername,
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
    )

    server_engine = create_engine(server_url, future=True)
    try:
        with server_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        server_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> None:
    """会话级：建库 + 按模型重建全部表。

    必须 **drop 后重建**，而不是只调 create_all：create_all 会跳过已存在的表，
    因此模型改了列（新增列、扩枚举取值）时它不会生效 —— 表现为一句莫名其妙的
    「Data truncated for column ...」，让人以为是代码写错了。
    MVP-1 之后本表结构一直没动，所以这个坑到 MVP-2 才暴露出来。

    重建前校验库名以 `_test` 结尾：本操作是破坏性的，若 DATABASE_URL 被外部
    环境变量指向了开发库或生产库，宁可报错也不能把它drop 掉。
    """
    url = get_settings().database_url
    db_name = make_url(url).database or ""
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"拒绝在非测试库上重建表：当前库名为 {db_name!r}。"
            "请在环境中设置 DATABASE_URL 指向以 `_test` 结尾的库。"
        )

    _ensure_database(url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _truncate_all() -> None:
    """清空全部业务表（保留结构），并重置自增。"""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """函数级：每个测试开始前清空数据。"""
    _truncate_all()


# ------------------------------ 基础夹具 ------------------------------


@pytest.fixture
def db():
    """直达数据库的会话（供 service / repository 层测试使用）。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """HTTP 测试客户端。

    raise_server_exceptions=False 让未预期异常走 500 处理器，
    从而可以断言「500 响应体不含堆栈」。
    """
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# ------------------------------ 用户夹具 ------------------------------


@pytest.fixture
def admin_user(db):
    from app.auth import service

    return service.create_user(db, "admin_test", "admin12345", "admin")


@pytest.fixture
def hr_user(db):
    from app.auth import service

    return service.create_user(db, "hr_test", "hr12345678", "hr")


@pytest.fixture
def admin_headers(admin_user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin_user.id)}"}


@pytest.fixture
def hr_headers(hr_user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(hr_user.id)}"}


@pytest.fixture
def other_hr(db):
    """第二个 hr 账号 —— 用于验证数据隔离。"""
    from app.auth import service

    return service.create_user(db, "hr_other", "hr12345678", "hr")


@pytest.fixture
def other_hr_headers(other_hr) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_hr.id)}"}


# ------------------------------ 候选人夹具 ------------------------------
# 这两个夹具是 module-12 / 13 / 14 / 16 测试的公共前置。


@pytest.fixture
def candidate_user(db):
    from app.auth import service

    return service.register_candidate(db, "cand_test", "cand12345678")


@pytest.fixture
def candidate_headers(candidate_user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(candidate_user.id)}"}


@pytest.fixture
def other_candidate(db):
    """第二个候选人 —— 用于验证候选人之间的数据隔离。"""
    from app.auth import service

    return service.register_candidate(db, "cand_other", "cand12345678")


@pytest.fixture
def other_candidate_headers(other_candidate) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(other_candidate.id)}"}


# ---------------------------- 业务夹具 ----------------------------

DEFAULT_DIMENSIONS = ["沟通能力", "专业能力", "逻辑思维"]


@pytest.fixture
def position(db, hr_user):
    """由 hr_user 创建的标准岗位。"""
    from app.position import service as position_service
    from app.position.schemas import PositionCreate

    return position_service.create_position(
        db,
        hr_user,
        PositionCreate(
            name="后端工程师",
            jd="负责后端服务的开发与维护，要求熟悉 Python 与数据库设计。",
            evaluation_dimensions=list(DEFAULT_DIMENSIONS),
        ),
    )


CANDIDATE_PASSWORD = "cand12345678"


@pytest.fixture
def accepted_interview(
    client, hr_headers, candidate_user, candidate_headers, position
) -> dict:
    """完整前置：HR 建面试 → 生成邀请码 → 候选人接受。

    返回 {interview_id, invitation_id, code, candidate_id}。
    供 module-12 / 14 / 15 的测试复用 —— 候选人侧的每个用例都需要一个
    「已接受邀请」的面试，逐处重写这段前置既啰嗦又容易漏一步。
    """
    interview = client.post(
        "/api/interviews",
        json={"position_id": position.id, "candidate_name": "张三"},
        headers=hr_headers,
    ).json()

    invitation = client.post(
        f"/api/interviews/{interview['id']}/invitations", headers=hr_headers
    ).json()

    accepted = client.post(
        f"/api/candidate/invitations/{invitation['code']}/accept",
        json={
            "username": candidate_user.username,
            "password": CANDIDATE_PASSWORD,
        },
        headers=candidate_headers,
    )
    assert accepted.status_code == 200, accepted.text

    return {
        "interview_id": interview["id"],
        "invitation_id": invitation["id"],
        "code": invitation["code"],
        "candidate_id": candidate_user.id,
    }
