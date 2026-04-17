"""Audit-trail tests for the per-issue submit contract.

Background — pre-fix bug: a single draft with multiple Jira issues could
end up with only one audit row when one issue was submitted manually and
the rest were auto-submitted by the scheduler. The manual single-issue
endpoint wrote per-issue, but the manual-all and scheduler paths wrote a
single batch row.

Post-fix contract: every issue submission — manual single, manual all,
auto — produces exactly one ``submitted_issue`` audit row, distinguished
by the ``source`` column.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from auto_daily_log.config import AutoApproveConfig
from auto_daily_log.models.database import Database
from auto_daily_log.scheduler.jobs import DailyWorkflow
from auto_daily_log.web.app import create_app


# Two-issue draft shape, matching what the LLM summary step produces.
TWO_ISSUE_SUMMARY = json.dumps([
    {"issue_key": "PROJ-100", "summary": "fixed parser", "time_spent_hours": 1.0},
    {"issue_key": "PROJ-101", "summary": "code review",  "time_spent_hours": 0.5},
])


@pytest_asyncio.fixture
async def env(tmp_path):
    db = Database(tmp_path / "audit.db", embedding_dimensions=4)
    await db.initialize()
    app = create_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db
    await db.close()


async def _seed_approved_two_issue_draft(db: Database, *, date: str = "2026-04-12") -> int:
    draft_id = await db.execute(
        "INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, "
        "status, tag, full_summary, created_at, updated_at) "
        "VALUES (?, 'PROJ-100', 5400, ?, 'approved', 'daily', 'two-issue test draft', "
        "datetime('now'), datetime('now'))",
        (date, TWO_ISSUE_SUMMARY),
    )
    await db.execute(
        "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'created', ?)",
        (draft_id, "{}"),
    )
    return draft_id


def _mock_publisher(returned_id: str = "12345"):
    """A WorklogPublisher stub that returns success with a fake worklog id."""
    from auto_daily_log.publishers import PublishResult
    pub = AsyncMock()
    pub.name = "jira"
    pub.submit = AsyncMock(return_value=PublishResult(
        success=True, worklog_id=returned_id, platform="jira",
        raw={"id": returned_id, "self": f"https://jira.test/rest/api/2/worklog/{returned_id}"},
    ))
    return pub


def _mock_jira(returned_id: str = "12345"):
    """A JiraClient stub for scheduler path (uses build_jira_client_from_db)."""
    jira = AsyncMock()
    jira.submit_worklog = AsyncMock(return_value={
        "id": returned_id,
        "self": f"https://jira.test/rest/api/2/worklog/{returned_id}",
    })
    return jira


# ── Mixed manual + auto: the original user-reported scenario ───────────

@pytest.mark.asyncio
async def test_mixed_manual_then_auto_writes_one_row_per_issue(env):
    """Issue 0 manually submitted, issue 1 auto-submitted later → 2 rows."""
    client, db = env
    draft_id = await _seed_approved_two_issue_draft(db)

    # Step 1: user manually submits the FIRST issue from the UI.
    with patch("auto_daily_log.web.api.worklogs._get_publisher",
               new=AsyncMock(return_value=_mock_publisher("manual-1"))), \
         patch("auto_daily_log.web.api.worklogs._get_started_timestamp",
               new=AsyncMock(return_value="2026-04-12T21:00:00.000+0800")):
        r = await client.post(f"/api/worklogs/{draft_id}/submit-issue/0")
    assert r.status_code == 200

    # Step 2: scheduler runs that night and picks up the remaining issue.
    auto_pub = _mock_publisher("auto-2")
    with patch("auto_daily_log.publishers.registry.get_publisher",
               new=AsyncMock(return_value=auto_pub)):
        wf = DailyWorkflow(db, MagicMock(), AutoApproveConfig(enabled=True, trigger_time="21:30"))
        await wf._submit_approved("2026-04-12")

    # ── Assertions ────────────────────────────────────────────────────
    rows = await db.fetch_all(
        "SELECT action, issue_index, issue_key, source FROM audit_logs "
        "WHERE draft_id = ? AND action = 'submitted_issue' "
        "ORDER BY issue_index",
        (draft_id,),
    )
    # Exactly TWO rows — one per issue, regardless of who triggered them.
    assert len(rows) == 2
    assert rows[0]["issue_index"] == 0
    assert rows[0]["issue_key"] == "PROJ-100"
    assert rows[0]["source"] == "manual_single"
    assert rows[1]["issue_index"] == 1
    assert rows[1]["issue_key"] == "PROJ-101"
    assert rows[1]["source"] == "auto"

    # Draft fully submitted → status flipped by the scheduler's all_done check.
    final = await db.fetch_one("SELECT status FROM worklog_drafts WHERE id = ?", (draft_id,))
    assert final["status"] == "submitted"

    # Publisher was called once for the remaining issue.
    assert auto_pub.submit.await_count == 1
    auto_call = auto_pub.submit.await_args
    assert auto_call.kwargs["issue_key"] == "PROJ-101"


# ── Manual submit-all path ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_submit_all_writes_one_row_per_issue(env):
    client, db = env
    draft_id = await _seed_approved_two_issue_draft(db)

    with patch("auto_daily_log.web.api.worklogs._get_publisher",
               new=AsyncMock(return_value=_mock_publisher("all-x"))), \
         patch("auto_daily_log.web.api.worklogs._get_started_timestamp",
               new=AsyncMock(return_value="2026-04-12T21:00:00.000+0800")):
        r = await client.post(f"/api/worklogs/{draft_id}/submit")
    assert r.status_code == 200

    rows = await db.fetch_all(
        "SELECT issue_index, issue_key, source FROM audit_logs "
        "WHERE draft_id = ? AND action = 'submitted_issue' "
        "ORDER BY issue_index",
        (draft_id,),
    )
    assert len(rows) == 2
    assert [r["issue_key"] for r in rows] == ["PROJ-100", "PROJ-101"]
    assert all(r["source"] == "manual_all" for r in rows)


# ── Per-issue failure isolation in the auto path ───────────────────────

@pytest.mark.asyncio
async def test_auto_submit_isolates_failure_to_one_issue(env):
    """If issue 0 fails to submit, issue 1 should still be attempted."""
    from auto_daily_log.publishers import PublishResult
    _client, db = env
    draft_id = await _seed_approved_two_issue_draft(db)

    call_count = {"n": 0}
    fail_then_ok = AsyncMock()
    fail_then_ok.name = "jira"
    async def _maybe_fail(*, issue_key, time_spent_sec, comment, started):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return PublishResult(success=False, platform="jira", error="Jira returned 502")
        return PublishResult(success=True, worklog_id="ok-2", platform="jira", raw={"id": "ok-2"})
    fail_then_ok.submit = _maybe_fail

    with patch("auto_daily_log.publishers.registry.get_publisher",
               new=AsyncMock(return_value=fail_then_ok)):
        wf = DailyWorkflow(db, MagicMock(), AutoApproveConfig(enabled=True, trigger_time="21:30"))
        await wf._submit_approved("2026-04-12")

    rows = await db.fetch_all(
        "SELECT action, issue_index, issue_key, source FROM audit_logs "
        "WHERE draft_id = ? AND action LIKE 'submit%' "
        "ORDER BY issue_index",
        (draft_id,),
    )
    assert len(rows) == 2
    assert rows[0]["action"] == "submit_failed_issue"
    assert rows[0]["issue_key"] == "PROJ-100"
    assert rows[0]["source"] == "auto"
    assert rows[1]["action"] == "submitted_issue"
    assert rows[1]["issue_key"] == "PROJ-101"
    assert rows[1]["source"] == "auto"

    # Draft NOT marked submitted because issue 0 still has no worklog id —
    # next scheduler run will retry it.
    final = await db.fetch_one("SELECT status FROM worklog_drafts WHERE id = ?", (draft_id,))
    assert final["status"] == "approved"


# ── Backward compat: legacy 'submitted' rows still surface ─────────────

@pytest.mark.asyncio
async def test_audit_trail_endpoint_returns_legacy_and_new_rows(env):
    """A pre-upgrade DB has batch 'submitted' rows. The audit endpoint
    must still return them so users don't lose history after the migration."""
    client, db = env
    draft_id = await _seed_approved_two_issue_draft(db)

    # Simulate a row written by the OLD batch path
    await db.execute(
        "INSERT INTO audit_logs (draft_id, action, jira_response) VALUES (?, 'submitted', ?)",
        (draft_id, json.dumps([{"issue_key": "PROJ-100", "jira_worklog_id": "old-1"}])),
    )
    # And one row written by the NEW per-issue path
    await db.execute(
        "INSERT INTO audit_logs (draft_id, action, jira_response, issue_index, issue_key, source) "
        "VALUES (?, 'submitted_issue', ?, 0, 'PROJ-100', 'manual_single')",
        (draft_id, json.dumps({"issue_key": "PROJ-100", "result": {"id": "new-1"}})),
    )

    r = await client.get(f"/api/worklogs/{draft_id}/audit")
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()]
    assert "submitted" in actions          # legacy preserved
    assert "submitted_issue" in actions    # new format
