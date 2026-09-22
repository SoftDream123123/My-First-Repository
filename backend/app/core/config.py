"""应用配置。

来源优先级：环境变量 > .env 文件 > 默认值。
必填项缺失时构造 Settings 即报错（fail fast），而非运行到一半才失败。
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 候选人反馈档位的**取值白名单**（PRD §4.9）。
#
# 与 ai.base 的 FEEDBACK_LEVELS 是同两个字符串，各自定义一份：core 不能 import ai
# （那会让 core ↔ ai 形成双向依赖，破坏分层单向）。这与 question_type 常量在
# question 与 ai 各定义一次是同一取舍 —— 模块解耦换来的重复，不是疏漏。
# 改这里必须同步改 ai.base.FEEDBACK_LEVELS。
CANDIDATE_FEEDBACK_LEVELS = ("summary", "full")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 必填 ----
    database_url: str
    jwt_secret: str

    # ---- 安全 ----
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720  # 12 小时
    bcrypt_rounds: int = 12

    # ---- AI Provider ----
    provider_name: str = "mock"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 1

    # ---- 出题数量（PRD §4.4）----
    question_count_from_bank: int = 5
    question_count_from_ai: int = 3

    # ---- 候选人侧（PRD §4.1）----
    # 候选人自助注册开关。默认开启以便开箱演示；生产部署应置为 false，
    # 此时候选人只能凭邀请码建号（凭邀请建号不受该开关影响）。
    candidate_self_register: bool = True

    # ---- 作答邀请（PRD §4.4）----
    # 邀请码有效期（天）。过期是**读取时派生**的，不落库、不需要调度器。
    invitation_expire_days: int = 7

    # ---- 按简历补题（PRD §4.14）----
    # 单次补题的默认追加题数；请求体可覆盖（上限 20，由 schema 固定）。
    # 进配置是因为它属**产品可调**的量：题太少展示不出效果、太多会让面试过长。
    resume_match_count: int = 3

    # ---- 刷题练习（PRD §4.7）----
    # 开始练习未指定题数时的默认题量
    practice_session_size_default: int = 10
    # 单次练习题量硬上限（防一次拉全库）
    practice_session_size_max: int = 20
    # 会话列表 limit 的硬上限
    practice_session_list_max: int = 100
    # 每用户每分钟的计分动作上限（**进程内**计数，故单机部署须 --workers 1）
    practice_rate_limit_per_minute: int = 60

    # ---- 简历（PRD §4.10）----
    # 简历正文长度上限。它是「避免超长文本打爆 AI 上下文」的护栏，与模型上下文
    # 长度绑死，将来换模型可能需要调，因此进配置而不是写死在 schema 里。
    resume_content_max_length: int = 20000

    # 简历文件上传的体积上限（PRD §4.10，MVP-4）。它同时是资源护栏：
    # 读上传文件时按 limit + 1 字节读，超限即拒，不必把整个大文件读进内存。
    # 注意它拦不住「请求体已被 Starlette 收完」这件事（见 module-25 §9-1），
    # 真正在请求发出前拦住大文件的是前端那道 file.size 预检。
    resume_upload_max_bytes: int = 5 * 1024 * 1024

    # ---- 候选人可见的评估反馈（PRD §4.9）----
    # summary（默认）仅下发综合结论 / 优点 / 待改进；full 额外下发总分。
    # 逐题分与维度分在任何档位都不下发。
    candidate_feedback_level: str = "summary"

    @field_validator("candidate_feedback_level")
    @classmethod
    def _check_feedback_level(cls, value: str) -> str:
        """取值非法则**拒绝启动**（fail fast）。

        它是部署配置：写错了应当立刻发现，而不是静默降级后让运维以为配置生效了。
        Provider 层还有一道防御（未知档位按 summary 处理），两层职责不同：
        这里拦住配置错误，那里保证调用方失误也不会泄露分数。
        """
        if value not in CANDIDATE_FEEDBACK_LEVELS:
            raise ValueError(
                f"CANDIDATE_FEEDBACK_LEVEL 取值非法：{value!r}；"
                f"可选值为 {CANDIDATE_FEEDBACK_LEVELS}"
            )
        return value

    # ---- 其他 ----
    cors_origins: list[str] = ["http://localhost:5173"]
    sql_echo: bool = False

    # ---- 初始管理员（seed 脚本使用）----
    admin_username: str = "admin"
    admin_password: str = "admin12345"


@lru_cache
def get_settings() -> Settings:
    """返回配置单例。

    使用 lru_cache 缓存；测试中可用 get_settings.cache_clear() 重置。
    """
    return Settings()
