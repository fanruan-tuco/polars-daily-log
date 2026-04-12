import json
from datetime import date
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["worklogs"])

class DraftSeed(BaseModel):
    date: str
    issue_key: str
    time_spent_sec: int
    summary: str

class DraftUpdate(BaseModel):
    time_spent_sec: Optional[int] = None
    summary: Optional[str] = None
    issue_key: Optional[str] = None

@router.get("/worklogs")
async def list_drafts(request: Request, date: str = Query(default=None), tag: str = Query(default=None)):
    db = request.app.state.db
    target = date or __import__("datetime").date.today().isoformat()
    if tag:
        return await db.fetch_all(
            "SELECT * FROM worklog_drafts WHERE tag = ? ORDER BY created_at DESC", (tag,)
        )
    return await db.fetch_all(
        "SELECT * FROM worklog_drafts WHERE date = ? ORDER BY created_at", (target,)
    )

class GenerateRequest(BaseModel):
    type: str  # daily, weekly, monthly, custom
    start_date: Optional[str] = None  # YYYY-MM-DD, for custom
    end_date: Optional[str] = None    # YYYY-MM-DD, for custom

@router.post("/worklogs/generate")
async def generate_summary(body: GenerateRequest, request: Request):
    """Generate worklog summary for a time period."""
    from datetime import date, timedelta
    db = request.app.state.db

    today = date.today()
    tag = body.type

    if tag == "daily":
        start = today.isoformat()
        end = today.isoformat()
    elif tag == "weekly":
        start = (today - timedelta(days=today.weekday())).isoformat()  # Monday
        end = today.isoformat()
    elif tag == "monthly":
        start = today.replace(day=1).isoformat()
        end = today.isoformat()
    elif tag == "custom":
        if not body.start_date or not body.end_date:
            raise HTTPException(400, "start_date and end_date required for custom type")
        start = body.start_date
        end = body.end_date
    else:
        raise HTTPException(400, f"Unknown type: {tag}")

    # Collect activities and commits for the date range
    activities = await db.fetch_all(
        "SELECT * FROM activities WHERE date(timestamp) >= ? AND date(timestamp) <= ? AND category != 'idle' ORDER BY timestamp",
        (start, end),
    )
    commits = await db.fetch_all(
        "SELECT * FROM git_commits WHERE date >= ? AND date <= ? ORDER BY committed_at",
        (start, end),
    )

    if not activities and not commits:
        raise HTTPException(404, f"No activity or commit data found for {start} to {end}")

    # Build summary text from data
    summary_parts = []

    # Group activities by category
    from collections import defaultdict
    cat_duration = defaultdict(int)
    for a in activities:
        cat_duration[a["category"]] += a.get("duration_sec", 0)

    if cat_duration:
        summary_parts.append("Activity summary:")
        for cat, sec in sorted(cat_duration.items(), key=lambda x: -x[1]):
            hours = round(sec / 3600, 1)
            summary_parts.append(f"  - {cat}: {hours}h")

    if commits:
        summary_parts.append(f"\nGit commits ({len(commits)}):")
        for c in commits[:20]:  # limit
            summary_parts.append(f"  - {c['message']}")

    total_sec = sum(a.get("duration_sec", 0) for a in activities)
    summary_text = "\n".join(summary_parts) if summary_parts else "No data"

    if tag == "daily":
        # Use existing seed approach - one draft per issue
        draft_id = await db.execute(
            "INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, status, tag, period_start, period_end) "
            "VALUES (?, ?, ?, ?, 'pending_review', ?, ?, ?)",
            (today.isoformat(), "ALL", total_sec, summary_text, tag, start, end),
        )
        await db.execute(
            "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'created', ?)",
            (draft_id, json.dumps({"tag": tag, "period": f"{start} to {end}"})),
        )
    else:
        # Non-daily: create as 'archived' directly (no approval needed)
        draft_id = await db.execute(
            "INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, status, tag, period_start, period_end) "
            "VALUES (?, ?, ?, ?, 'archived', ?, ?, ?)",
            (today.isoformat(), "SUMMARY", total_sec, summary_text, tag, start, end),
        )
        await db.execute(
            "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'created', ?)",
            (draft_id, json.dumps({"tag": tag, "period": f"{start} to {end}"})),
        )

    return {"id": draft_id, "tag": tag, "period_start": start, "period_end": end}

@router.post("/worklogs/seed", status_code=201)
async def seed_draft(body: DraftSeed, request: Request):
    db = request.app.state.db
    draft_id = await db.execute(
        "INSERT INTO worklog_drafts (date, issue_key, time_spent_sec, summary, status) VALUES (?, ?, ?, ?, 'pending_review')",
        (body.date, body.issue_key, body.time_spent_sec, body.summary),
    )
    await db.execute(
        "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'created', ?)",
        (draft_id, json.dumps(body.model_dump(), ensure_ascii=False)),
    )
    return {"id": draft_id}

@router.patch("/worklogs/{draft_id}")
async def update_draft(draft_id: int, body: DraftUpdate, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    if not existing:
        raise HTTPException(404, "Draft not found")
    before = json.dumps(dict(existing), ensure_ascii=False, default=str)
    updates = ["user_edited = 1", "updated_at = datetime('now')"]
    params = []
    if body.time_spent_sec is not None: updates.append("time_spent_sec = ?"); params.append(body.time_spent_sec)
    if body.summary is not None: updates.append("summary = ?"); params.append(body.summary)
    if body.issue_key is not None: updates.append("issue_key = ?"); params.append(body.issue_key)
    params.append(draft_id)
    await db.execute(f"UPDATE worklog_drafts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    updated = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    after = json.dumps(dict(updated), ensure_ascii=False, default=str)
    await db.execute("INSERT INTO audit_logs (draft_id, action, before_snapshot, after_snapshot) VALUES (?, 'edited', ?, ?)", (draft_id, before, after))
    return {"status": "updated"}

@router.post("/worklogs/{draft_id}/approve")
async def approve_draft(draft_id: int, request: Request):
    db = request.app.state.db
    await db.execute("UPDATE worklog_drafts SET status = 'approved', updated_at = datetime('now') WHERE id = ?", (draft_id,))
    await db.execute("INSERT INTO audit_logs (draft_id, action) VALUES (?, 'approved')", (draft_id,))
    return {"status": "approved"}

@router.post("/worklogs/{draft_id}/reject")
async def reject_draft(draft_id: int, request: Request):
    db = request.app.state.db
    await db.execute("UPDATE worklog_drafts SET status = 'rejected', updated_at = datetime('now') WHERE id = ?", (draft_id,))
    await db.execute("INSERT INTO audit_logs (draft_id, action) VALUES (?, 'rejected')", (draft_id,))
    return {"status": "rejected"}

@router.post("/worklogs/approve-all")
async def approve_all(request: Request, date: str = Query(default=None)):
    db = request.app.state.db
    target = date or __import__("datetime").date.today().isoformat()
    await db.execute("UPDATE worklog_drafts SET status = 'approved', updated_at = datetime('now') WHERE date = ? AND status = 'pending_review'", (target,))
    drafts = await db.fetch_all("SELECT id FROM worklog_drafts WHERE date = ? AND status = 'approved'", (target,))
    for d in drafts:
        await db.execute("INSERT INTO audit_logs (draft_id, action) VALUES (?, 'approved')", (d["id"],))
    return {"status": "all_approved", "count": len(drafts)}

@router.post("/worklogs/{draft_id}/submit")
async def submit_to_jira(draft_id: int, request: Request):
    db = request.app.state.db
    draft = await db.fetch_one("SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,))
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft["status"] not in ("approved", "auto_approved"):
        raise HTTPException(400, f"Draft status is '{draft['status']}', must be approved first")

    jira_url = await db.fetch_one("SELECT value FROM settings WHERE key = 'jira_server_url'")
    jira_pat = await db.fetch_one("SELECT value FROM settings WHERE key = 'jira_pat'")
    if not jira_url or not jira_pat or not jira_url["value"] or not jira_pat["value"]:
        raise HTTPException(400, "Jira not configured. Set server URL and PAT in Settings.")

    from ...config import JiraConfig
    from ...jira_client.client import JiraClient
    jira_config = JiraConfig(server_url=jira_url["value"], pat=jira_pat["value"])
    jira = JiraClient(jira_config)

    started = f"{draft['date']}T09:00:00.000+0800"
    try:
        result = await jira.submit_worklog(issue_key=draft["issue_key"], time_spent_sec=draft["time_spent_sec"], comment=draft["summary"], started=started)
        jira_worklog_id = result.get("id", "")
    except Exception as e:
        raise HTTPException(502, f"Jira API error: {str(e)}")

    await db.execute("UPDATE worklog_drafts SET status = 'submitted', jira_worklog_id = ?, updated_at = datetime('now') WHERE id = ?", (str(jira_worklog_id), draft_id))
    await db.execute("INSERT INTO audit_logs (draft_id, action, jira_response) VALUES (?, 'submitted', ?)", (draft_id, json.dumps(result, ensure_ascii=False)))
    return {"status": "submitted", "jira_worklog_id": jira_worklog_id}

@router.get("/worklogs/{draft_id}/audit")
async def get_audit_trail(draft_id: int, request: Request):
    db = request.app.state.db
    return await db.fetch_all("SELECT * FROM audit_logs WHERE draft_id = ? ORDER BY created_at", (draft_id,))
