"""SMS Provider 工厂测试：配置切换、缓存、fail fast。

与 `test_ai_factory.py` **逐项同构** —— 两个包既然同构，测试也该是同一套，
否则「同构」只是一句说法，下一个人看不出哪些行为是约定、哪些是巧合。
"""

import pytest

from app.core.config import get_settings
from app.core.exceptions import SmsProviderError
from app.sms import factory
from app.sms.base import SmsProvider, mask_phone
from app.sms.mock_provider import MockSmsProvider


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """每个测试前后都清空配置与 Provider 缓存。"""
    get_settings.cache_clear()
    factory.reset_provider_cache()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    factory.reset_provider_cache()


def test_returns_mock_by_default():
    assert isinstance(factory.get_provider(), MockSmsProvider)


def test_mock_conforms_to_abstract():
    assert isinstance(factory.get_provider(), SmsProvider)


def test_mock_echoes_code():
    """Mock 的全部意义就是让开发 / 演示拿到码，因此它必须回显。"""
    assert factory.get_provider().echoes_code is True


def test_invalid_name_raises(monkeypatch):
    """取值非法时拒绝启动，**不静默退回 Mock**（PRD §6）。

    静默退回的后果最严重：生产会把验证码写进日志并回显给浏览器，
    而运行为一切正常。
    """
    monkeypatch.setenv("SMS_PROVIDER", "aliyun")
    get_settings.cache_clear()

    with pytest.raises(SmsProviderError):
        factory.get_provider()


def test_caches_instance():
    assert factory.get_provider() is factory.get_provider()


def test_reset_cache_returns_new_instance():
    first = factory.get_provider()
    factory.reset_provider_cache()
    assert factory.get_provider() is not first


def test_validate_provider_config_passes_for_mock():
    factory.validate_provider_config()  # 不抛异常即通过


def test_provider_name_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "MOCK")
    get_settings.cache_clear()
    assert isinstance(factory.get_provider(), MockSmsProvider)


class TestMaskPhone:
    """手机号是 PII，日志里一律掩码（PRD §6）。"""

    def test_normal(self):
        assert mask_phone("13800138000") == "138****8000"

    def test_keeps_first_three_and_last_four(self):
        assert mask_phone("19912345678") == "199****5678"

    def test_short_input_is_fully_masked(self):
        """短于 7 位整体掩码，不做切片。

        正常输入不会这么短，但这是唯一一个把手机号写进日志的公共入口 ——
        切片越界或原样漏出去都是不可接受的失败方向。
        """
        assert mask_phone("1380") == "****"
        assert mask_phone("") == ""

    def test_no_digits_leak_for_short_input(self):
        assert "1" not in mask_phone("123456")
