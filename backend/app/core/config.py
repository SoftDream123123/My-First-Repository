"""应用配置。

来源优先级：环境变量 > .env 文件 > 默认值。
必填项缺失时构造 Settings 即报错（fail fast），而非运行到一半才失败。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
