import pytest
from auto_daily_log.summarizer.engine import get_llm_engine, LLMEngine
from auto_daily_log.config import LLMConfig, LLMProviderConfig


def test_get_openai_compat_engine():
    config = LLMConfig(engine="openai_compat", openai_compat=LLMProviderConfig(
        api_key="test-key", model="moonshot-v1-8k", base_url="https://api.moonshot.cn/v1"
    ))
    engine = get_llm_engine(config)
    assert isinstance(engine, LLMEngine)
    assert engine.name == "openai_compat"


def test_get_anthropic_engine():
    config = LLMConfig(engine="anthropic", anthropic=LLMProviderConfig(
        api_key="test-key", model="claude-sonnet-4-20250514", base_url="https://api.anthropic.com"
    ))
    engine = get_llm_engine(config)
    assert engine.name == "anthropic"


def test_get_ollama_engine():
    config = LLMConfig(engine="ollama", ollama=LLMProviderConfig(
        model="llama3", base_url="http://localhost:11434"
    ))
    engine = get_llm_engine(config)
    assert engine.name == "ollama"


def test_unknown_engine_raises():
    config = LLMConfig(engine="unknown")
    with pytest.raises(ValueError, match="Unknown LLM engine"):
        get_llm_engine(config)
