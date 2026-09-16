"""Provider 工厂测试：配置切换、缓存、fail fast。"""

import pytest

from app.ai import factory
from app.ai.base import AIProvider
from app.ai.mock_provider import MockProvider
from app.core.config import get_settings
from app.core.exceptions import AIProviderError


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
    assert isinstance(factory.get_provider(), MockProvider)


def test_mock_conforms_to_abstract():
    assert isinstance(factory.get_provider(), AIProvider)


def test_returns_openai_when_configured(monkeypatch):
    monkeypatch.setenv("PROVIDER_NAME", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    get_settings.cache_clear()

    from app.ai.openai_provider import OpenAIProvider

    provider = factory.get_provider()
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider, AIProvider)
    provider.close()


def test_invalid_name_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER_NAME", "bogus")
    get_settings.cache_clear()

    with pytest.raises(AIProviderError):
        factory.get_provider()


def test_openai_without_key_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER_NAME", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(AIProviderError):
        factory.get_provider()


def test_openai_without_base_url_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER_NAME", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(AIProviderError):
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
    monkeypatch.setenv("PROVIDER_NAME", "MOCK")
    get_settings.cache_clear()
    assert isinstance(factory.get_provider(), MockProvider)
