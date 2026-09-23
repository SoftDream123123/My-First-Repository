"""Provider 工厂：按配置返回实现并缓存单例。

与 `ai/factory.py` **逐项同构**（单例缓存 + `reset_provider_cache` + 启动期校验），
是为了让「Provider 该在哪儿接入」这件事在两个包里有同一个答案。
"""

from app.core.config import get_settings
from app.core.exceptions import SmsProviderError
from app.sms.base import SmsProvider
from app.sms.mock_provider import MockSmsProvider

PROVIDER_MOCK = "mock"

#: 本批次**只有 Mock** —— 真实 Provider 待接入运营商时再实现（PRD §1.3）。
#: 真接入时在这里加取值与一个分支即可，调用方（auth）无需改动。
KNOWN_PROVIDERS = (PROVIDER_MOCK,)

_cache: SmsProvider | None = None


def _build() -> SmsProvider:
    name = get_settings().sms_provider.strip().lower()

    if name == PROVIDER_MOCK:
        return MockSmsProvider()

    # 延迟导入的位置留给真实实现（如 `from app.sms.aliyun_provider import …`）。
    raise SmsProviderError(
        f"未知的 SMS Provider：{name!r}；可选值为 {KNOWN_PROVIDERS}"
    )


def get_provider() -> SmsProvider:
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

    由 main.py 在装配阶段调用，避免「服务起来了但第一次发码才报错」。

    ⚠️ 这里**不能静默退回 Mock**：那样生产会在无人察觉的情况下把验证码写进
    日志并回显给浏览器（§6）。配置写错就该起不来。
    """
    get_provider()
