import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from auto_daily_log.scheduler.jobs import DailyWorkflow
from auto_daily_log.models.database import Database
from auto_daily_log.config import AutoApproveConfig


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db", embedding_dimensions=4)
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_auto_approve_approves_draft_with_issue_entries(db):
    """auto_approve_pending marks drafts with non-empty per-issue JSON as auto_approved.
    No LLM call is made — refinement already happened at generation time."""
    issue_entries = [
        {"issue_key": "PROJ-101", "time_spent_hours": 1.0, "summary": "修复了 SQL 解析器"}
    ]
    draft_id = await db.execute(
        """INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, full_summary, status, tag)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-04-12", "DAILY", 3600, json.dumps(issue_entries), "raw summary text", "pending_review", "daily"),
    )

    mock_engine = AsyncMock()  # should never be called
    workflow = DailyWorkflow(db, mock_engine, AutoApproveConfig(enabled=True, trigger_time="21:30"))
    await workflow.auto_approve_pending("2026-04-12")

    assert mock_engine.generate.await_count == 0
    draft = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    assert draft["status"] == "auto_approved"

    logs = await db.fetch_all("SELECT * FROM audit_logs WHERE draft_id = ?", (draft_id,))
    assert any(l["action"] == "auto_approved" for l in logs)


@pytest.mark.asyncio
async def test_auto_approve_skips_draft_with_empty_entries(db):
    """Drafts whose refined JSON is empty (LLM found no work content) stay pending."""
    draft_id = await db.execute(
        """INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, full_summary, status, tag)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-04-12", "DAILY", 0, "[]", "今天主要在看视频和闲聊", "pending_review", "daily"),
    )

    mock_engine = AsyncMock()
    workflow = DailyWorkflow(db, mock_engine, AutoApproveConfig(enabled=True, trigger_time="21:30"))
    await workflow.auto_approve_pending("2026-04-12")

    assert mock_engine.generate.await_count == 0
    draft = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    assert draft["status"] == "pending_review"

    logs = await db.fetch_all("SELECT * FROM audit_logs WHERE draft_id = ?", (draft_id,))
    assert any(l["action"] == "auto_skipped" for l in logs)


@pytest.mark.asyncio
async def test_auto_approve_disabled_is_noop(db):
    draft_id = await db.execute(
        """INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, full_summary, status, tag)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2026-04-12", "DAILY", 3600, json.dumps([{"issue_key": "PROJ-101", "time_spent_hours": 1, "summary": "x"}]),
         "raw", "pending_review", "daily"),
    )
    workflow = DailyWorkflow(db, AsyncMock(), AutoApproveConfig(enabled=False, trigger_time="21:30"))
    await workflow.auto_approve_pending("2026-04-12")

    draft = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    assert draft["status"] == "pending_review"
