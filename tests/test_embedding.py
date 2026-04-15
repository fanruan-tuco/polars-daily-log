import pytest
from auto_daily_log.search.embedding import get_embedding_engine, EmbeddingEngine, OpenAICompatibleEmbedding, OllamaEmbedding
from auto_daily_log.config import LLMConfig, LLMProviderConfig, EmbeddingConfig


def test_openai_compat_embedding_engine():
    llm_config = LLMConfig(engine="openai_compat", openai_compat=LLMProviderConfig(
        api_key="test-key", base_url="https://api.moonshot.cn/v1"
    ))
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert isinstance(engine, OpenAICompatibleEmbedding)
    assert engine.dimensions == 1024


def test_ollama_embedding_engine():
    llm_config = LLMConfig(engine="ollama", ollama=LLMProviderConfig(
        base_url="http://localhost:11434"
    ))
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert isinstance(engine, OllamaEmbedding)


def test_anthropic_no_embedding():
    llm_config = LLMConfig(engine="anthropic")
    emb_config = EmbeddingConfig(enabled=True)
    engine = get_embedding_engine(llm_config, emb_config)
    assert engine is None


def test_disabled_returns_none():
    llm_config = LLMConfig(engine="openai_compat")
    emb_config = EmbeddingConfig(enabled=False)
    engine = get_embedding_engine(llm_config, emb_config)
    assert engine is None
