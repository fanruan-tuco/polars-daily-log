import httpx
from ..config import LLMProviderConfig
from .engine import LLMEngine

class ClaudeEngine(LLMEngine):
    name = "anthropic"
    def __init__(self, config: LLMProviderConfig):
        self._config = config
    async def generate(self, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise Exception("Empty prompt provided to LLM engine")
        base_url = (self._config.base_url or "https://api.anthropic.com").rstrip("/")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/v1/messages",
                headers={"x-api-key": self._config.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": self._config.model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]},
            )
            if response.status_code != 200:
                error_body = response.text[:500]
                raise Exception(f"LLM API error {response.status_code}: {error_body}")
            return response.json()["content"][0]["text"]
