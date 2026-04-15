import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from auto_daily_log.summarizer.summarizer import WorklogSummarizer
from auto_daily_log.summarizer.prompt import (
    DEFAULT_SUMMARIZE_PROMPT,
    DEFAULT_AUTO_APPROVE_PROMPT,
    render_prompt,
)
from auto_daily_log.models.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db", embedding_dimensions=4)
    await database.initialize()
    yield database
    await database.close()


def test_default_summarize_prompt_has_placeholders():
    """Step 1 prompt: raw activity summary — no jira issues yet."""
    assert "{date}" in DEFAULT_SUMMARIZE_PROMPT
    assert "{git_commits}" in DEFAULT_SUMMARIZE_PROMPT
    assert "{activities}" in DEFAULT_SUMMARIZE_PROMPT


def test_default_auto_approve_prompt_has_placeholders():
    """Step 2 prompt: refine into Jira entries using step-1 output."""
    assert "{date}" in DEFAULT_AUTO_APPROVE_PROMPT
    assert "{jira_issues}" in DEFAULT_AUTO_APPROVE_PROMPT
    assert "{full_summary}" in DEFAULT_AUTO_APPROVE_PROMPT
    assert "{git_commits}" in DEFAULT_AUTO_APPROVE_PROMPT


def test_render_prompt_summarize():
    rendered = render_prompt(
        DEFAULT_SUMMARIZE_PROMPT,
        date="2026-04-12",
        git_commits="- 10:30 fix: resolve JOIN issue",
        activities="- 9:00-11:00 IntelliJ (Main.java) coding",
    )
    assert "2026-04-12" in rendered
    assert "IntelliJ" in rendered
    assert "JOIN issue" in rendered


def test_render_prompt_auto_approve():
    rendered = render_prompt(
        DEFAULT_AUTO_APPROVE_PROMPT,
        date="2026-04-12",
        jira_issues="- PROJ-101: Fix SQL parser",
        full_summary="今天修复了 SQL 解析器的 JOIN 问题",
        git_commits="- 10:30 fix: resolve JOIN issue",
    )
    assert "PROJ-101" in rendered
    assert "2026-04-12" in rendered
    assert "JOIN 问题" in rendered


@pytest.mark.asyncio
async def test_summarizer_generates_single_daily_draft(db):
    """Two-step pipeline: one DAILY draft per day with per-issue JSON in summary + full_summary."""
    await db.execute(
        "INSERT INTO jira_issues (issue_key, summary, description, is_active) VALUES (?, ?, ?, ?)",
        ("PROJ-101", "Fix SQL parser", "Fix JOIN handling in parser", 1),
    )
    await db.execute(
        """INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("2026-04-12T10:00:00", "IntelliJ IDEA", "AstToPlanConverter.java", "coding", 0.92, 3600),
    )

    # Step 1: raw full_summary text. Step 2: JSON per-issue array.
    mock_engine = AsyncMock()
    mock_engine.generate.side_effect = [
        "今天在 IntelliJ IDEA 里修改了 AstToPlanConverter.java，约 1 小时。",
        json.dumps([
            {"issue_key": "PROJ-101", "time_spent_hours": 1.0, "summary": "修复了SQL解析器的JOIN处理逻辑"}
        ]),
    ]

    summarizer = WorklogSummarizer(db, mock_engine)
    drafts = await summarizer.generate_drafts("2026-04-12")

    assert len(drafts) == 1
    assert drafts[0]["issue_key"] == "DAILY"
    assert drafts[0]["time_spent_sec"] == 3600
    assert "IntelliJ" in drafts[0]["full_summary"]

    issue_entries = json.loads(drafts[0]["summary"])
    assert len(issue_entries) == 1
    assert issue_entries[0]["issue_key"] == "PROJ-101"
    assert issue_entries[0]["time_spent_hours"] == 1.0

    rows = await db.fetch_all("SELECT * FROM worklog_drafts WHERE date = '2026-04-12'")
    assert len(rows) == 1
    assert rows[0]["status"] == "pending_review"
    assert rows[0]["tag"] == "daily"

    logs = await db.fetch_all("SELECT * FROM audit_logs")
    assert len(logs) == 1
    assert logs[0]["action"] == "created"


@pytest.mark.asyncio
async def test_summarizer_invokes_activity_backfill(db):
    """generate_drafts must call activity_summarizer.backfill_for_date up front."""
    await db.execute(
        """INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("2026-04-12T10:00:00", "VSCode", "main.py", "coding", 0.9, 60),
    )

    mock_engine = AsyncMock()
    mock_engine.generate.side_effect = ["full summary text", "[]"]

    backfill_calls = []

    class FakeActivitySummarizer:
        async def backfill_for_date(self, target_date, timeout_sec):
            backfill_calls.append((target_date, timeout_sec))
            return 0

    fake = FakeActivitySummarizer()
    summarizer = WorklogSummarizer(db, mock_engine, activity_summarizer=fake)
    await summarizer.generate_drafts("2026-04-12")

    assert len(backfill_calls) == 1
    assert backfill_calls[0] == ("2026-04-12", 60)


@pytest.mark.asyncio
async def test_summarizer_backfill_failure_is_non_fatal(db):
    """If backfill raises, daily generation must still proceed."""
    await db.execute(
        """INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("2026-04-12T10:00:00", "VSCode", "main.py", "coding", 0.9, 60),
    )

    mock_engine = AsyncMock()
    mock_engine.generate.side_effect = ["full summary text", "[]"]

    class ExplodingSummarizer:
        async def backfill_for_date(self, target_date, timeout_sec):
            raise RuntimeError("simulated backfill crash")

    summarizer = WorklogSummarizer(
        db, mock_engine, activity_summarizer=ExplodingSummarizer()
    )
    drafts = await summarizer.generate_drafts("2026-04-12")

    # Draft creation continues after non-fatal backfill failure
    assert len(drafts) == 1
    assert drafts[0]["issue_key"] == "DAILY"
