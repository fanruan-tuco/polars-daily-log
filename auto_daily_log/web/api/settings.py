from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

router = APIRouter(tags=["settings"])

class SettingUpdate(BaseModel):
    value: str


class LLMCheckRequest(BaseModel):
    engine: str
    api_key: str
    model: Optional[str] = ""
    base_url: Optional[str] = ""


@router.post("/settings/check-llm")
async def check_llm_key(body: LLMCheckRequest):
    """Validate LLM API key by making a minimal test call."""
    defaults = {
        "kimi": ("moonshot-v1-8k", "https://api.moonshot.cn/v1"),
        "openai": ("gpt-4o", "https://api.openai.com/v1"),
        "ollama": ("llama3", "http://localhost:11434"),
        "claude": ("claude-sonnet-4-20250514", "https://api.anthropic.com"),
    }
    default_model, default_url = defaults.get(body.engine, ("", ""))
    model = body.model or default_model
    base_url = body.base_url or default_url

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if body.engine == "ollama":
                # Ollama: just check if server is reachable
                resp = await client.get(f"{base_url}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    return {"valid": True, "message": f"Ollama connected. Models: {', '.join(models[:5])}"}
                return {"valid": False, "message": f"Ollama unreachable: {resp.status_code}"}

            elif body.engine == "claude":
                resp = await client.post(
                    f"{base_url}/v1/messages",
                    headers={"x-api-key": body.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                )
            else:
                # OpenAI-compatible (Kimi, OpenAI)
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {body.api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                )

            if resp.status_code == 200:
                return {"valid": True, "message": f"Key valid. Engine: {body.engine}, Model: {model}"}
            elif resp.status_code == 401:
                return {"valid": False, "message": "API Key invalid or expired (401 Unauthorized)"}
            elif resp.status_code == 403:
                return {"valid": False, "message": "Access denied (403 Forbidden). Check key permissions."}
            elif resp.status_code == 429:
                return {"valid": True, "message": "Key valid (rate limited). Engine working."}
            else:
                error_text = resp.text[:200]
                return {"valid": False, "message": f"Error {resp.status_code}: {error_text}"}
    except httpx.ConnectError:
        return {"valid": False, "message": f"Cannot connect to {base_url}. Check URL."}
    except httpx.TimeoutException:
        return {"valid": False, "message": f"Connection timeout to {base_url}"}
    except Exception as e:
        return {"valid": False, "message": f"Error: {str(e)}"}

@router.get("/settings/default-prompts")
async def get_default_prompts():
    """Return all default prompt templates — single source of truth."""
    from ...summarizer.prompt import (
        DEFAULT_SUMMARIZE_PROMPT,
        DEFAULT_AUTO_APPROVE_PROMPT,
        DEFAULT_PERIOD_SUMMARY_PROMPT,
    )
    return {
        "summarize_prompt": DEFAULT_SUMMARIZE_PROMPT,
        "auto_approve_prompt": DEFAULT_AUTO_APPROVE_PROMPT,
        "period_summary_prompt": DEFAULT_PERIOD_SUMMARY_PROMPT,
    }


@router.get("/settings")
async def list_settings(request: Request):
    db = request.app.state.db
    return await db.fetch_all("SELECT key, value, updated_at FROM settings")

@router.get("/settings/{key}")
async def get_setting(key: str, request: Request):
    db = request.app.state.db
    row = await db.fetch_one("SELECT * FROM settings WHERE key = ?", (key,))
    return row or {"key": key, "value": None}

@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingUpdate, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT key FROM settings WHERE key = ?", (key,))
    if existing:
        await db.execute("UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = ?", (body.value, key))
    else:
        await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, body.value))
    return {"key": key, "value": body.value}
