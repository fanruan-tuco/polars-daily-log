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
async def list_drafts(request: Request, date: str = Query(default=None)):
    db = request.app.state.db
    target = date or __import__("datetime").date.today().isoformat()
    return await db.fetch_all("SELECT * FROM worklog_drafts WHERE date = ? ORDER BY created_at", (target,))

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
