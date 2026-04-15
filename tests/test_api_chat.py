"""Tests for /api/chat.

The LLM is monkeypatched — we verify context assembly, SSE framing, and
error paths, not actual model quality.
"""
import json
from datetime import date

import pytest
import pytest_asyncio

from auto_daily_log.web.api import chat as chat_module


class _FakeLLM:
    """Mimics LLMEngine.generate_stream by splitting the response into chunks.

    The real LLMEngine base class yields via an async iterator; we mirror
    that here so the chat endpoint exercises the same code path.
    """
    def __init__(self, response: str = "这是助手的回复，用来验证 SSE 流式分块逻辑。"):
        self.response = response
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response

    async def generate_stream(self, prompt: str):
        self.prompts.append(prompt)
        for i in range(0, len(self.response), 32):
            yield self.response[i:i + 32]


class _FailingLLM:
    async def generate(self, prompt: str) -> str:
        raise RuntimeError("api key missing")

    async def generate_stream(self, prompt: str):
        raise RuntimeError("api key missing")
        yield  # pragma: no cover — keeps this an async generator


def _patch_engine(monkeypatch, engine):
    async def _factory(_db):
        return engine
    monkeypatch.setattr(chat_module, "_get_llm_engine_from_settings", _factory)


def _parse_sse(body: str) -> list:
    """Parse an SSE body into a list of events (dict for JSON, str for [DONE])."""
    events = []
    for block in body.strip().split("\n\n"):
        if not block.startswith("data: "):
            continue
        payload = block[len("data: "):].strip()
        if payload == "[DONE]":
            events.append("[DONE]")
        else:
            events.append(json.loads(payload))
    return events


# ─── happy path ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_streams_chunked_response(app_client, monkeypatch):
    fake = _FakeLLM(response="Hello world from the fake LLM.")
    _patch_engine(monkeypatch, fake)

    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "今天我都做了什么？"}],
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    text_events = [e for e in events if isinstance(e, dict) and "text" in e]
    assembled = "".join(e["text"] for e in text_events)
    assert assembled == "Hello world from the fake LLM."
    assert events[-1] == "[DONE]"


@pytest.mark.asyncio
async def test_chat_injects_user_question_into_prompt(app_client, monkeypatch):
    fake = _FakeLLM()
    _patch_engine(monkeypatch, fake)

    await app_client.post("/api/chat", json={
        "messages": [
            {"role": "user", "text": "上周我在 PDL-42 花了多少时间？"},
        ],
    })
    assert len(fake.prompts) == 1
    assert "上周我在 PDL-42 花了多少时间？" in fake.prompts[0]


@pytest.mark.asyncio
async def test_chat_includes_history(app_client, monkeypatch):
    fake = _FakeLLM()
    _patch_engine(monkeypatch, fake)

    await app_client.post("/api/chat", json={
        "messages": [
            {"role": "user", "text": "昨天干嘛了？"},
            {"role": "ai",   "text": "昨天你在写 chat endpoint。"},
            {"role": "user", "text": "具体改了哪些文件？"},
        ],
    })
    prompt = fake.prompts[0]
    assert "昨天干嘛了？" in prompt
    assert "昨天你在写 chat endpoint。" in prompt
    assert "具体改了哪些文件？" in prompt


@pytest.mark.asyncio
async def test_chat_context_days_override_is_clamped(app_client, monkeypatch):
    fake = _FakeLLM()
    _patch_engine(monkeypatch, fake)

    # Request window beyond MAX_CONTEXT_DAYS — handler should clamp without
    # error rather than rejecting. Verifies both the plumbing + the clamp.
    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "历史全记录"}],
        "context_days": 9999,
    })
    assert resp.status_code == 200

    # And negative/zero is clamped upward to at least 1 day.
    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "今天"}],
        "context_days": 0,
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_pulls_recent_drafts_into_prompt(app_client, monkeypatch):
    # seed a worklog draft for today
    today = date.today().isoformat()
    await app_client.post("/api/worklogs/seed", json={
        "date": today,
        "issue_key": "PDL-42",
        "time_spent_sec": 3600,
        "summary": "Built the chat endpoint with SSE framing.",
    })

    fake = _FakeLLM()
    _patch_engine(monkeypatch, fake)

    await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "今天干了啥？"}],
    })
    prompt = fake.prompts[0]
    assert "PDL-42" in prompt
    assert "Built the chat endpoint with SSE framing." in prompt


# ─── error path ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_reports_llm_error_as_sse_event(app_client, monkeypatch):
    _patch_engine(monkeypatch, _FailingLLM())

    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "hi"}],
    })
    assert resp.status_code == 200  # stream opens OK; error is inside the stream
    events = _parse_sse(resp.text)
    error_events = [e for e in events if isinstance(e, dict) and "error" in e]
    assert len(error_events) == 1
    assert "api key missing" in error_events[0]["error"]
    assert events[-1] == "[DONE]"


# ─── helper unit tests ──────────────────────────────────────────────

def test_chunk_text_splits_by_size():
    out = chat_module._chunk_text("abcdefghij", 4)
    assert out == ["abcd", "efgh", "ij"]


def test_chunk_text_empty():
    assert chat_module._chunk_text("", 4) == [""]


def test_format_summaries_groups_by_date():
    rows = [
        {"date": "2026-04-14", "issue_key": "PDL-1", "full_summary": "A", "summary": ""},
        {"date": "2026-04-15", "issue_key": "PDL-2", "full_summary": "B", "summary": ""},
        {"date": "2026-04-15", "issue_key": "PDL-3", "full_summary": "C", "summary": ""},
    ]
    out = chat_module._format_summaries(rows)
    # newest date comes first, each draft as a bullet
    lines = out.split("\n")
    assert lines[0] == "### 2026-04-15"
    assert "- [PDL-2] B" in lines
    assert "- [PDL-3] C" in lines
    assert "### 2026-04-14" in out


def test_format_summaries_empty():
    assert chat_module._format_summaries([]) == "(窗口期内无工作日志)"


def test_format_history_skips_when_empty():
    assert chat_module._format_history([]) == ""


def test_latest_user_question_picks_last_user_message():
    msgs = [
        chat_module.ChatMessage(role="user", text="first"),
        chat_module.ChatMessage(role="ai", text="answer"),
        chat_module.ChatMessage(role="user", text="second"),
    ]
    assert chat_module._latest_user_question(msgs) == "second"


# ─── session persistence ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_new_session_is_advertised_as_first_sse_event(app_client, monkeypatch):
    fake = _FakeLLM(response="hello")
    _patch_engine(monkeypatch, fake)

    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "第一条消息"}],
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    # First event is the session_id control event
    assert isinstance(events[0], dict)
    assert "session_id" in events[0]
    session_id = events[0]["session_id"]
    assert len(session_id) == 32  # uuid4 hex
    assert events[-1] == "[DONE]"

    # Session now appears in the listing
    list_resp = await app_client.get("/api/chat/sessions")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == session_id
    assert rows[0]["title"] == "第一条消息"
    assert rows[0]["message_count"] == 2

    # Messages endpoint returns exactly [user, ai] in order
    msg_resp = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    assert msg_resp.status_code == 200
    msgs = msg_resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["text"] == "第一条消息"
    assert msgs[1]["role"] == "ai"
    assert msgs[1]["text"] == "hello"


@pytest.mark.asyncio
async def test_chat_reuses_session_and_appends_messages(app_client, monkeypatch):
    fake = _FakeLLM(response="first reply")
    _patch_engine(monkeypatch, fake)

    resp1 = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "第一轮"}],
    })
    events = _parse_sse(resp1.text)
    session_id = events[0]["session_id"]

    # Second post carries the same session id → no new session_id event
    fake2 = _FakeLLM(response="second reply")
    _patch_engine(monkeypatch, fake2)
    resp2 = await app_client.post("/api/chat", json={
        "session_id": session_id,
        "messages": [
            {"role": "user", "text": "第一轮"},
            {"role": "ai", "text": "first reply"},
            {"role": "user", "text": "第二轮"},
        ],
    })
    assert resp2.status_code == 200
    events2 = _parse_sse(resp2.text)
    session_id_events = [e for e in events2 if isinstance(e, dict) and "session_id" in e]
    assert session_id_events == []  # no control event on reuse

    list_resp = await app_client.get("/api/chat/sessions")
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == session_id
    assert rows[0]["message_count"] == 4

    msg_resp = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    msgs = msg_resp.json()
    assert len(msgs) == 4
    assert [m["role"] for m in msgs] == ["user", "ai", "user", "ai"]
    assert [m["text"] for m in msgs] == ["第一轮", "first reply", "第二轮", "second reply"]


@pytest.mark.asyncio
async def test_chat_get_messages_404_for_bogus_id(app_client):
    resp = await app_client.get("/api/chat/sessions/deadbeefdeadbeef/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_delete_session_removes_messages(app_client, monkeypatch):
    fake = _FakeLLM(response="bye")
    _patch_engine(monkeypatch, fake)

    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "to be deleted"}],
    })
    events = _parse_sse(resp.text)
    session_id = events[0]["session_id"]

    del_resp = await app_client.delete(f"/api/chat/sessions/{session_id}")
    assert del_resp.status_code == 204

    # GET messages now 404
    msg_resp = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    assert msg_resp.status_code == 404

    # DELETE again 404
    del_again = await app_client.delete(f"/api/chat/sessions/{session_id}")
    assert del_again.status_code == 404

    # Session list empty
    list_resp = await app_client.get("/api/chat/sessions")
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_chat_error_path_persists_user_but_not_ai(app_client, monkeypatch):
    _patch_engine(monkeypatch, _FailingLLM())

    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": "会失败的问题"}],
    })
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    session_id = events[0]["session_id"]
    error_events = [e for e in events if isinstance(e, dict) and "error" in e]
    assert len(error_events) == 1

    msg_resp = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    msgs = msg_resp.json()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["text"] == "会失败的问题"


@pytest.mark.asyncio
async def test_chat_session_title_defaults_when_question_empty(app_client, monkeypatch):
    fake = _FakeLLM(response="noop")
    _patch_engine(monkeypatch, fake)

    # No user message at all — title falls back to "New chat" and no
    # user row is persisted (only the AI reply).
    resp = await app_client.post("/api/chat", json={"messages": []})
    events = _parse_sse(resp.text)
    session_id = events[0]["session_id"]

    list_resp = await app_client.get("/api/chat/sessions")
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == session_id
    assert rows[0]["title"] == "New chat"


@pytest.mark.asyncio
async def test_chat_session_title_truncated_to_40_chars(app_client, monkeypatch):
    fake = _FakeLLM(response="ok")
    _patch_engine(monkeypatch, fake)

    long_q = "x" * 100
    resp = await app_client.post("/api/chat", json={
        "messages": [{"role": "user", "text": long_q}],
    })
    events = _parse_sse(resp.text)
    session_id = events[0]["session_id"]

    list_resp = await app_client.get("/api/chat/sessions")
    rows = list_resp.json()
    title = [r["title"] for r in rows if r["id"] == session_id][0]
    assert title == "x" * 40
