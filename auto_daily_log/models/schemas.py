from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ActivityRecord(BaseModel):
    id: Optional[int] = None
    timestamp: str
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    url: Optional[str] = None
    signals: Optional[str] = None
    duration_sec: int = 30


class GitRepo(BaseModel):
    id: Optional[int] = None
    path: str
    author_email: Optional[str] = None
    is_active: bool = True


class GitCommit(BaseModel):
    id: Optional[int] = None
    repo_id: int
    hash: str
    message: Optional[str] = None
    author: Optional[str] = None
    committed_at: Optional[str] = None
    files_changed: Optional[str] = None
    insertions: int = 0
    deletions: int = 0
    date: str


class JiraIssue(BaseModel):
    id: Optional[int] = None
    issue_key: str
    summary: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class WorklogDraft(BaseModel):
    id: Optional[int] = None
    date: str
    issue_key: str
    time_spent_sec: int = 0
    summary: Optional[str] = None
    raw_activities: Optional[str] = None
    raw_commits: Optional[str] = None
    status: str = "pending_review"
    user_edited: bool = False
    jira_worklog_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AuditLog(BaseModel):
    id: Optional[int] = None
    draft_id: int
    action: str
    before_snapshot: Optional[str] = None
    after_snapshot: Optional[str] = None
    jira_response: Optional[str] = None
    created_at: Optional[str] = None


class SettingItem(BaseModel):
    key: str
    value: str


class WorklogDraftUpdate(BaseModel):
    time_spent_sec: Optional[int] = None
    summary: Optional[str] = None
    issue_key: Optional[str] = None
    status: Optional[str] = None
