"""Provider 工厂：按配置返回实现并缓存单例。

Provider 实例无状态，缓存单例避免每次调用重新构造
（真实 Provider 可复用底层 httpx 连接池）。
"""

from app.ai.base import AIProvider
from app.ai.mock_provider import MockProvider
from app.core.config import get_settings
from app.core.exceptions import AIProviderError

PROVIDER_MOCK = "mock"
PROVIDER_OPENAI = "openai"
KNOWN_PROVIDERS = (PROVIDER_MOCK, PROVIDER_OPENAI)

_cache: AIProvider | None = None


def _build() -> AIProvider:
    name = get_settings().provider_name.strip().lower()

    if name == PROVIDER_MOCK:
        return MockProvider()

    if name == PROVIDER_OPENAI:
        # 延迟导入：mock 模式下无需加载 httpx 相关代码
        from app.ai.openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise AIProviderError(
        f"未知的 AI Provider：{name!r}；可选值为 {KNOWN_PROVIDERS}"
    )


def get_provider() -> AIProvider:
    """返回当前配置对应的 Provider 实例（单例）。"""
    global _cache
    if _cache is None:
        _cache = _build()
    return _cache


def reset_provider_cache() -> None:
    """清空单例缓存 —— 供测试切换实现使用。"""
    global _cache
    _cache = None


def validate_provider_config() -> None:
    """启动期校验 Provider 配置，配置有误则直接失败（fail fast）。

    由 main.py 在装配阶段调用，避免「服务起来了但第一次调用 AI 才报错」。
    """
    get_provider()
