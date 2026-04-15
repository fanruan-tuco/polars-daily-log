"""Feedback endpoint — records user feedback as a Jira worklog.

Implementation detail: feedback becomes a 1-minute worklog on an
internal tracking issue. The issue key stays server-side so the
user-facing UI doesn't leak it.
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...jira_client.client import MissingJiraConfig, build_jira_client_from_db

router = APIRouter(tags=["feedback"])

# Internal tracking issue. Keep in code, not in client responses.
_FEEDBACK_ISSUE_KEY = "PLS-4626"
_FEEDBACK_TIME_SEC = 60  # 1 minute; Jira worklog minimum

_TYPE_LABELS = {
    "bug": "[BUG]",
    "suggestion": "[建议]",
    "other": "[反馈]",
}


class FeedbackRequest(BaseModel):
    type: str
    content: str
    page: str = ""
    user_agent: str = ""


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, request: Request):
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "反馈内容不能为空")
    if len(content) > 2000:
        raise HTTPException(400, "反馈内容过长（上限 2000 字）")

    db = request.app.state.db
    try:
        jira = await build_jira_client_from_db(db)
    except MissingJiraConfig as e:
        raise HTTPException(503, str(e))

    username = (await db.fetch_one("SELECT value FROM settings WHERE key = 'jira_username'") or {}).get("value", "")

    label = _TYPE_LABELS.get(body.type, _TYPE_LABELS["other"])
    now = datetime.now()
    # JiraClient._build_worklog_payload strips 4-byte UTF-8 automatically.
    comment = (
        f"{label}\n\n"
        f"{content}\n\n"
        f"---\n"
        f"Page: {body.page or 'unknown'} · Time: {now.strftime('%Y-%m-%d %H:%M')}"
        f"{' · User: ' + username if username else ''}\n"
        f"UA: {body.user_agent[:200] if body.user_agent else 'unknown'}"
    )

    started = now.strftime("%Y-%m-%dT%H:%M:%S.000+0800")
    try:
        result = await jira.submit_worklog(
            issue_key=_FEEDBACK_ISSUE_KEY,
            time_spent_sec=_FEEDBACK_TIME_SEC,
            comment=comment,
            started=started,
        )
    except Exception as e:
        raise HTTPException(502, f"提交失败：{e}")

    # Return success only — do NOT leak the issue key.
    return {"ok": True, "worklog_id": str(result.get("id", ""))}
