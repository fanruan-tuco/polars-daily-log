from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ..config import LLMConfig, LLMProviderConfig, EmbeddingConfig

_DEFAULT_MODELS = {
    "kimi": ("moonshot-v1-embedding", 1024),
    "openai": ("text-embedding-3-small", 1536),
    "ollama": ("nomic-embed-text", 768),
}


class EmbeddingEngine(ABC):
    dimensions: int

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class OpenAICompatibleEmbedding(EmbeddingEngine):
    def __init__(self, config: LLMProviderConfig, model: str, dimensions: int):
        self._config = config
        self._model = model
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": text},
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()["data"]
            return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]


class OllamaEmbedding(EmbeddingEngine):
    def __init__(self, config: LLMProviderConfig, model: str, dimensions: int):
        self._config = config
        self._model = model
        self.dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._config.base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            response.raise_for_status()
            return response.json()["embedding"]


def get_embedding_engine(
    llm_config: LLMConfig, emb_config: EmbeddingConfig
) -> Optional[EmbeddingEngine]:
    if not emb_config.enabled:
        return None

    engine_name = llm_config.engine.lower()
    default_model, default_dims = _DEFAULT_MODELS.get(engine_name, ("", 1536))
    model = emb_config.model or default_model
    dimensions = emb_config.dimensions or default_dims

    if engine_name == "kimi":
        return OpenAICompatibleEmbedding(llm_config.kimi, model, dimensions)
    elif engine_name == "openai":
        return OpenAICompatibleEmbedding(llm_config.openai, model, dimensions)
    elif engine_name == "ollama":
        return OllamaEmbedding(llm_config.ollama, model, dimensions)
    elif engine_name == "claude":
        return None
    return None
