"""LLM engine factory.

Three canonical protocols:
  - openai_compat : OpenAI-compatible API (OpenAI, Kimi, DeepSeek, 智谱, ...)
  - anthropic     : Claude / Anthropic Messages API
  - ollama        : Ollama local API
"""
from abc import ABC, abstractmethod

from ..config import LLMConfig

VALID_PROTOCOLS = ("openai_compat", "anthropic", "ollama")


class LLMEngine(ABC):
    name: str

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...


def get_llm_engine(config: LLMConfig) -> LLMEngine:
    protocol = (config.engine or "openai_compat").lower()

    if protocol == "openai_compat":
        from .openai_compat import OpenAICompatEngine
        return OpenAICompatEngine(config.openai_compat)

    if protocol == "anthropic":
        from .claude_engine import ClaudeEngine
        return ClaudeEngine(config.anthropic)

    if protocol == "ollama":
        from .ollama import OllamaEngine
        return OllamaEngine(config.ollama)

    raise ValueError(f"Unknown LLM engine/protocol: {config.engine}")
