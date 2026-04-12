import pytest
from auto_daily_log.search.embedding import get_embedding_engine, EmbeddingEngine
from auto_daily_log.config import LLMConfig, LLMProviderConfig, EmbeddingConfig

def test_get_kimi_embedding_engine():
    llm_config = LLMConfig(engine="kimi", kimi=LLMProviderConfig(
        api_key="test-key", base_url="https://api.moonshot.cn/v1"
    ))
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert isinstance(engine, EmbeddingEngine)
    assert engine.dimensions > 0

def test_get_openai_embedding_engine():
    llm_config = LLMConfig(engine="openai", openai=LLMProviderConfig(
        api_key="test-key", base_url="https://api.openai.com/v1"
    ))
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert isinstance(engine, EmbeddingEngine)

def test_get_ollama_embedding_engine():
    llm_config = LLMConfig(engine="ollama", ollama=LLMProviderConfig(
        base_url="http://localhost:11434"
    ))
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert isinstance(engine, EmbeddingEngine)

def test_disabled_returns_none():
    llm_config = LLMConfig(engine="kimi")
    emb_config = EmbeddingConfig(enabled=False)
    engine = get_embedding_engine(llm_config, emb_config)
    assert engine is None
