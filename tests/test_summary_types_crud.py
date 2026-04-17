"""Tests for summary types CRUD API + WebhookPublisher."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport, AsyncClient

from auto_daily_log.models.database import Database
from auto_daily_log.publishers import PublishResult, WorklogPublisher
from auto_daily_log.publishers.webhook import WebhookPublisher
from auto_daily_log.web.app import create_app


@pytest_asyncio.fixture
async def env(tmp_path):
    db = Database(tmp_path / "crud.db", embedding_dimensions=4)
    await db.initialize()
    app = create_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db
    await db.close()


# ══════════════════════════════════════════════════════════════════════
# CRUD API
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_custom_type(env):
    client, _db = env
    r = await client.post("/api/summary-types", json={
        "name": "sprint-review",
        "display_name": "Sprint 回顾",
        "scope_rule": '{"type":"week"}',
        "review_mode": "manual",
        "publisher_name": "webhook",
        "publisher_config": '{"url":"https://example.com/hook","format":"generic"}',
    })
    assert r.status_code == 201
    assert r.json() == {"name": "sprint-review", "status": "created"}

    types = (await client.get("/api/summary-types")).json()
    names = [t["name"] for t in types]
    assert "sprint-review" in names
    custom = next(t for t in types if t["name"] == "sprint-review")
    assert custom["is_builtin"] == 0
    assert custom["publisher_name"] == "webhook"


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(env):
    client, _db = env
    r = await client.post("/api/summary-types", json={
        "name": "daily",
        "display_name": "重复日报",
        "scope_rule": '{"type":"day"}',
    })
    assert r.status_code == 409
    assert "已存在" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_invalid_scope_returns_400(env):
    client, _db = env
    r = await client.post("/api/summary-types", json={
        "name": "bad-scope",
        "display_name": "坏范围",
        "scope_rule": '{"type":"invalid"}',
    })
    assert r.status_code == 400
    assert "scope_rule.type" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_invalid_review_mode_returns_400(env):
    client, _db = env
    r = await client.post("/api/summary-types", json={
        "name": "bad-review",
        "display_name": "坏审批",
        "scope_rule": '{"type":"day"}',
        "review_mode": "semi-auto",
    })
    assert r.status_code == 400
    assert "review_mode" in r.json()["detail"]


@pytest.mark.asyncio
async def test_update_builtin_type(env):
    client, _db = env
    r = await client.put("/api/summary-types/daily", json={
        "review_mode": "manual",
        "publisher_name": "webhook",
    })
    assert r.status_code == 200
    assert r.json() == {"name": "daily", "status": "updated"}
    daily = next(t for t in (await client.get("/api/summary-types")).json() if t["name"] == "daily")
    assert daily["review_mode"] == "manual"
    assert daily["publisher_name"] == "webhook"


@pytest.mark.asyncio
async def test_update_nonexistent_returns_404(env):
    client, _db = env
    r = await client.put("/api/summary-types/nope", json={"review_mode": "auto"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_no_fields_returns_400(env):
    client, _db = env
    r = await client.put("/api/summary-types/daily", json={})
    assert r.status_code == 400
    assert "没有要更新的字段" in r.json()["detail"]


@pytest.mark.asyncio
async def test_delete_custom_type(env):
    client, _db = env
    await client.post("/api/summary-types", json={
        "name": "throwaway",
        "display_name": "临时",
        "scope_rule": '{"type":"day"}',
    })
    r = await client.delete("/api/summary-types/throwaway")
    assert r.status_code == 200
    assert r.json() == {"name": "throwaway", "status": "deleted"}
    names = [t["name"] for t in (await client.get("/api/summary-types")).json()]
    assert "throwaway" not in names


@pytest.mark.asyncio
async def test_delete_builtin_returns_403(env):
    client, _db = env
    r = await client.delete("/api/summary-types/daily")
    assert r.status_code == 403
    assert "不能删除" in r.json()["detail"]


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(env):
    client, _db = env
    r = await client.delete("/api/summary-types/nope")
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# WebhookPublisher
# ══════════════════════════════════════════════════════════════════════

def test_webhook_publisher_is_worklog_publisher():
    pub = WebhookPublisher({"url": "https://example.com/hook"})
    assert isinstance(pub, WorklogPublisher)
    assert pub.name == "webhook"
    assert pub.display_name == "Webhook"


@pytest.mark.asyncio
async def test_webhook_submit_missing_url():
    pub = WebhookPublisher({})
    result = await pub.submit(issue_key="X-1", time_spent_sec=3600, comment="test", started="2026-04-17T21:00")
    assert result.success is False
    assert result.error == "webhook URL 未配置"
    assert result.platform == "webhook"


@pytest.mark.asyncio
async def test_webhook_generic_format_body():
    pub = WebhookPublisher({"url": "https://example.com", "format": "generic"})
    body = pub._build_body(issue_key="PLS-1", time_spent_sec=5400, comment="coding", started="2026-04-17T21:00")
    assert body == {
        "issue_key": "PLS-1",
        "time_spent_sec": 5400,
        "time_spent_hours": 1.5,
        "comment": "coding",
        "started": "2026-04-17T21:00",
    }


@pytest.mark.asyncio
async def test_webhook_wecom_format_body():
    pub = WebhookPublisher({"url": "https://qyapi.weixin.qq.com/hook", "format": "wecom"})
    body = pub._build_body(issue_key="PLS-2", time_spent_sec=7200, comment="review", started="2026-04-17T21:00")
    assert body == {
        "msgtype": "text",
        "text": {"content": "[PLS-2] 2.0h — review"},
    }


@pytest.mark.asyncio
async def test_webhook_feishu_format_body():
    pub = WebhookPublisher({"url": "https://feishu.cn/hook", "format": "feishu"})
    body = pub._build_body(issue_key="PLS-3", time_spent_sec=1800, comment="meeting", started="2026-04-17T21:00")
    assert body == {
        "msg_type": "text",
        "content": {"text": "[PLS-3] 0.5h — meeting"},
    }


@pytest.mark.asyncio
async def test_webhook_slack_format_body():
    pub = WebhookPublisher({"url": "https://hooks.slack.com/xxx", "format": "slack"})
    body = pub._build_body(issue_key="PLS-4", time_spent_sec=3600, comment="deploy", started="2026-04-17T21:00")
    assert body == {"text": "[PLS-4] 1.0h — deploy"}


@pytest.mark.asyncio
async def test_webhook_submit_success(httpx_mock):
    """Real HTTP via httpx mock — verifies the full submit path."""
    # We can't use httpx_mock fixture (not installed), so mock at transport level
    from unittest.mock import patch, MagicMock

    pub = WebhookPublisher({"url": "https://example.com/hook", "format": "generic"})

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = '{"ok":true}'

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        result = await pub.submit(issue_key="X-1", time_spent_sec=3600, comment="test", started="2026-04-17T21:00")
    assert result.success is True
    assert result.worklog_id == "webhook-200"
    assert result.platform == "webhook"


@pytest.mark.asyncio
async def test_webhook_submit_http_error():
    from unittest.mock import patch, MagicMock
    pub = WebhookPublisher({"url": "https://example.com/hook"})
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.text = "Internal Server Error"
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        result = await pub.submit(issue_key="X-1", time_spent_sec=3600, comment="test", started="2026-04-17T21:00")
    assert result.success is False
    assert "HTTP 500" in result.error


@pytest.mark.asyncio
async def test_webhook_submit_timeout():
    from unittest.mock import patch
    pub = WebhookPublisher({"url": "https://example.com/hook", "timeout": 1})
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
        result = await pub.submit(issue_key="X-1", time_spent_sec=3600, comment="test", started="2026-04-17T21:00")
    assert result.success is False
    assert "超时" in result.error


# ══════════════════════════════════════════════════════════════════════
# Registry resolves webhook with per-type config
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_registry_resolves_webhook_with_config(env):
    client, db = env
    await client.post("/api/summary-types", json={
        "name": "wecom-daily",
        "display_name": "企微日报",
        "scope_rule": '{"type":"day"}',
        "publisher_name": "webhook",
        "publisher_config": '{"url":"https://qyapi.weixin.qq.com/hook?key=abc","format":"wecom"}',
    })
    from auto_daily_log.publishers.registry import get_publisher
    pub = await get_publisher(db, "wecom-daily")
    assert pub.name == "webhook"
    assert pub._url == "https://qyapi.weixin.qq.com/hook?key=abc"
    assert pub._format == "wecom"
